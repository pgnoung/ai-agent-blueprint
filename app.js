// AI Agent ตัวแรกของคุณ — builds the LINE message and opens the chat with the OA, pre-filled.
// Nothing is sent anywhere by this page: the text reaches the OA only when the person presses ส่ง in LINE.
'use strict';

(() => {
  const URL_LIMIT = 1999;               // the line.me link must stay under 2,000 characters
  const NEAR_LIMIT = 0.85;              // show the remaining-room hint from 85% of the limit
  const COUNT_NEAR = 0.9;               // per-field counter turns gold from 90% of maxlength
  const MIN_CHARS = 2;
  const THAI_URL_COST = 9;              // one Thai character = 3 UTF-8 bytes = 9 URL characters
  const MESSAGE_BASE = 'https://line.me/R/oaMessage/';
  const FRIEND_BASE = 'https://line.me/R/ti/p/';
  const DRAFT_KEY = 'ai-agent-blueprint.draft';

  const MSG = {
    businessEmpty: 'กรุณาใส่ธุรกิจของคุณ',
    answerEmpty: 'กรุณาเขียนงานที่อยากมอบหมายให้ผู้ช่วย',
    tooShort: 'เขียนเพิ่มอีกนิด ให้เราเข้าใจได้',
    over: (n) => `ข้อความยาวเกินที่ LINE รับได้ · ลดอีก ${n} ตัวอักษร`,
    near: (n) => `LINE รับได้อีกประมาณ ${n} ตัวอักษร`,
    config: 'ตั้งค่าหน้านี้ไม่ครบ กรุณาแจ้งทีมงาน',
  };

  // ---------- pure helpers ----------
  // encodeURIComponent throws on half an emoji, so drop unpaired surrogates (no lookbehind: older iOS).
  function dropLoneSurrogates(text) {
    let out = '';
    for (let i = 0; i < text.length; i += 1) {
      const code = text.charCodeAt(i);
      if (code >= 0xD800 && code <= 0xDBFF) {
        const next = text.charCodeAt(i + 1);
        if (next >= 0xDC00 && next <= 0xDFFF) {
          out += text[i] + text[i + 1];
          i += 1;
        }
      } else if (code < 0xDC00 || code > 0xDFFF) {
        out += text[i];
      }
    }
    return out;
  }

  function normalize(value) {
    return dropLoneSurrogates(String(value || ''))
      .replace(/[\r\n\t\v\f\u2028\u2029]+/g, ' ')
      .replace(/\s{2,}/g, ' ')
      .trim();
  }

  function buildText(campaign, business, answer) {
    return [
      `${campaign.keyword} ${campaign.campaignId}`,
      `ธุรกิจ: ${business}`,
      `อยากให้ผู้ช่วย AI ทำก่อน: ${answer}`,
      campaign.requestLine,
    ].join('\n');
  }

  function buildMessageUrl(oa, text) {
    return `${MESSAGE_BASE}${encodeURIComponent(oa)}/?${encodeURIComponent(text)}`;
  }

  function buildFriendUrl(oa) {
    return `${FRIEND_BASE}${encodeURIComponent(oa)}`;
  }

  // How many characters must go (from the end of the answer, then the business) to fit under URL_LIMIT.
  function charsToCut(campaign, business, answer) {
    let excess = buildMessageUrl(campaign.oa, buildText(campaign, business, answer)).length - URL_LIMIT;
    if (excess <= 0) return 0;
    let cut = 0;
    for (const source of [Array.from(answer), Array.from(business)]) {
      while (source.length && excess > 0) {
        excess -= encodeURIComponent(source.pop()).length;
        cut += 1;
      }
    }
    return cut;
  }

  // ---------- config ----------
  function readConfig() {
    const node = document.getElementById('campaigns');
    const config = JSON.parse(node ? node.textContent : '');
    const campaigns = config && config.campaigns;
    if (!campaigns || typeof campaigns !== 'object' || !campaigns[config.default]) {
      throw new Error('campaign config: missing "campaigns" or "default"');
    }
    return config;
  }

  function pickCampaign(config, search) {
    const requested = (new URLSearchParams(search).get('c') || '').trim().toUpperCase();
    const campaign = campaigns(config)[requested] || config.campaigns[config.default];
    for (const key of ['campaignId', 'keyword', 'oa', 'requestLine']) {
      if (typeof campaign[key] !== 'string' || !campaign[key].trim()) {
        throw new Error(`campaign config: "${key}" is missing`);
      }
    }
    return campaign;
  }

  function campaigns(config) {
    // case-insensitive lookup so ?c=iesa6 works too
    const byUpper = {};
    for (const [id, value] of Object.entries(config.campaigns)) byUpper[id.toUpperCase()] = value;
    return byUpper;
  }

  // ---------- storage (per-tab convenience only; the page works without it) ----------
  function loadDraft() {
    try {
      const raw = window.sessionStorage.getItem(DRAFT_KEY);
      const draft = raw ? JSON.parse(raw) : null;
      return draft && typeof draft === 'object' ? draft : null;
    } catch {
      return null;
    }
  }

  function saveDraft(draft) {
    try {
      window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch {
      /* storage blocked: the draft simply is not kept */
    }
  }

  // ---------- UI ----------
  function init() {
    const els = {
      page: document.querySelector('.page'),
      form: document.getElementById('blueprint-form'),
      formView: document.getElementById('form-view'),
      doneView: document.getElementById('done-view'),
      doneTitle: document.getElementById('done-title'),
      preview: document.getElementById('preview'),
      friend: document.getElementById('friend-link'),
      resend: document.getElementById('resend-link'),
      edit: document.getElementById('edit-button'),
      budget: document.getElementById('budget'),
      fields: {
        business: document.getElementById('business'),
        answer: document.getElementById('answer'),
      },
    };

    let campaign;
    try {
      campaign = pickCampaign(readConfig(), window.location.search);
    } catch (err) {
      console.error(err);
      els.budget.textContent = MSG.config;
      els.budget.classList.add('is-over');
      els.budget.hidden = false;
      els.form.querySelector('button[type="submit"]').disabled = true;
      return;
    }

    document.querySelectorAll('[data-bind="kicker"]').forEach((n) => { if (campaign.kicker) n.textContent = campaign.kicker; });
    document.querySelectorAll('[data-bind="oa"]').forEach((n) => { n.textContent = campaign.oa; });
    els.friend.href = buildFriendUrl(campaign.oa);

    const draft = loadDraft();
    if (draft) {
      for (const name of ['business', 'answer']) {
        const field = els.fields[name];
        if (!field.value && typeof draft[name] === 'string') field.value = draft[name].slice(0, field.maxLength);
      }
    }

    const values = () => ({
      business: normalize(els.fields.business.value),
      answer: normalize(els.fields.answer.value),
    });

    // Grow a textarea with its text where CSS field-sizing is not supported (older Safari).
    function fitTextarea(area) {
      if (window.CSS && CSS.supports && CSS.supports('field-sizing', 'content')) return;
      area.style.height = 'auto';
      area.style.height = `${area.scrollHeight + 3}px`;
    }

    function updateCount(name) {
      const field = els.fields[name];
      const counter = document.getElementById(`${name}-count`);
      const length = field.value.length;
      counter.textContent = `${length}/${field.maxLength}`;
      counter.classList.toggle('is-near', length >= field.maxLength * COUNT_NEAR);
    }

    function setError(name, message) {
      const field = els.fields[name];
      const error = document.getElementById(`${name}-error`);
      error.textContent = message || '';
      error.hidden = !message;
      if (message) field.setAttribute('aria-invalid', 'true');
      else field.removeAttribute('aria-invalid');
    }

    function updateBudget() {
      const { business, answer } = values();
      const length = buildMessageUrl(campaign.oa, buildText(campaign, business, answer)).length;
      const cut = charsToCut(campaign, business, answer);
      if (cut > 0) {
        els.budget.textContent = MSG.over(cut);
        els.budget.classList.add('is-over');
        els.budget.hidden = false;
      } else if (length >= URL_LIMIT * NEAR_LIMIT) {
        const room = Math.max(0, Math.floor((URL_LIMIT - length) / THAI_URL_COST));
        els.budget.textContent = MSG.near(room);
        els.budget.classList.remove('is-over');
        els.budget.hidden = false;
      } else {
        els.budget.textContent = '';
        els.budget.classList.remove('is-over');
        els.budget.hidden = true;
      }
      return cut;
    }

    function validate() {
      const { business, answer } = values();
      const problems = [];
      const check = (name, value, emptyMessage) => {
        const message = !value ? emptyMessage : value.length < MIN_CHARS ? MSG.tooShort : '';
        setError(name, message);
        if (message) problems.push(name);
      };
      check('business', business, MSG.businessEmpty);
      check('answer', answer, MSG.answerEmpty);
      const cut = updateBudget();
      if (!problems.length && cut > 0) problems.push(answer ? 'answer' : 'business');
      return { ok: problems.length === 0, first: problems[0], business, answer };
    }

    function showDone(text, url) {
      els.preview.textContent = text;
      els.resend.href = url;
      els.formView.hidden = true;
      els.doneView.hidden = false;
      els.page.classList.add('is-sent');
      els.doneTitle.focus({ preventScroll: true });
      window.scrollTo({ top: 0 });
    }

    function showForm() {
      els.doneView.hidden = true;
      els.formView.hidden = false;
      els.page.classList.remove('is-sent');
      els.fields.answer.focus();
    }

    for (const name of ['business', 'answer']) {
      const field = els.fields[name];
      field.addEventListener('input', () => {
        updateCount(name);
        if (field.getAttribute('aria-invalid') === 'true' && normalize(field.value).length >= MIN_CHARS) setError(name, '');
        updateBudget();
        fitTextarea(field);
        saveDraft({ business: els.fields.business.value, answer: els.fields.answer.value });
      });
      updateCount(name);
    }

    // Enter in the business box moves on to the answer (never during IME composition).
    els.fields.business.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' || event.isComposing || event.keyCode === 229) return;
      event.preventDefault();
      els.fields.answer.focus();
    });

    els.form.addEventListener('submit', (event) => {
      event.preventDefault();
      const result = validate();
      if (!result.ok) {
        els.fields[result.first].focus();
        return;
      }
      const text = buildText(campaign, result.business, result.answer);
      const url = buildMessageUrl(campaign.oa, text);
      showDone(text, url);
      window.location.assign(url);
    });

    els.edit.addEventListener('click', showForm);

    updateBudget();
    fitTextarea(els.fields.business);
    fitTextarea(els.fields.answer);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
