(function (root) {
  'use strict';
  const FIELDS = ['play_name', 'materials', 'support_direction'];
  class PlanEditor {
    constructor(data, curriculum, saved = null) {
      this.data = data; this.curriculum = curriculum;
      this.periods = data.periods.map(p => p.period_key);
      this.rows = Object.fromEntries(data.periods.map(p => [p.period_key, Object.fromEntries(p.rows.map(r => [r.candidate_id, r]))]));
      this.contents = Object.fromEntries(curriculum.map(c => [c.id, c]));
      this.state = {version: 1, source: data.run_id, selected: {}, slots: {}, edits: {}};
      for (const p of this.periods) { this.state.selected[p] = []; this.state.slots[p] = Array(5).fill(null); }
      if (saved) this.restore(saved);
    }
    restore(saved) {
      if (saved.version !== 1 || saved.source !== this.data.run_id) return false;
      const next = JSON.parse(JSON.stringify(saved));
      for (const p of this.periods) {
        const selected = next.selected?.[p], slots = next.slots?.[p];
        if (!Array.isArray(selected) || selected.length > 5 || new Set(selected).size !== selected.length || selected.some(id => !this.rows[p][id])) return false;
        if (!Array.isArray(slots) || slots.length !== 5 || slots.some(id => id !== null && !selected.includes(id))) return false;
        if (new Set(slots.filter(Boolean)).size !== slots.filter(Boolean).length) return false;
      }
      if (!next.edits || typeof next.edits !== 'object') return false;
      for (const [key, edit] of Object.entries(next.edits)) {
        const [p, id] = key.split(':');
        if (!this.rows[p]?.[id] || !edit || typeof edit !== 'object') return false;
        if (Object.keys(edit).some(k => ![...FIELDS, 'learning_content_ids'].includes(k))) return false;
        if (FIELDS.some(k => edit[k] !== undefined && typeof edit[k] !== 'string')) return false;
        if (edit.learning_content_ids && !this.validLearning(edit.learning_content_ids)) return false;
      }
      this.state = next; return true;
    }
    snapshot() { return JSON.parse(JSON.stringify(this.state)); }
    validLearning(ids) { return Array.isArray(ids) && ids.length >= 2 && ids.length <= 3 && new Set(ids).size === ids.length && ids.every(id => !!this.contents[id]); }
    row(p, id) {
      const original = this.rows[p]?.[id]; if (!original) throw new Error('UNKNOWN_PLAY');
      const row = {...original, ...this.state.edits[`${p}:${id}`]};
      row.learning = row.learning_content_ids.map(id => this.contents[id].display).join('\n'); return row;
    }
    edited(p, id) { return Object.keys(this.state.edits[`${p}:${id}`] || {}).length > 0; }
    toggle(p, id) {
      if (!this.rows[p]?.[id]) throw new Error('UNKNOWN_PLAY');
      const chosen = this.state.selected[p], at = chosen.indexOf(id);
      if (at >= 0) { chosen.splice(at, 1); this.state.slots[p] = this.state.slots[p].map(x => x === id ? null : x); return false; }
      if (chosen.length === 5) throw new Error('FIVE_PLAYS_ONLY');
      chosen.push(id); return true;
    }
    arrange(p) {
      const chosen = this.state.selected[p], slots = this.state.slots[p];
      for (const id of chosen) if (!slots.includes(id)) { const at = slots.indexOf(null); if (at >= 0) slots[at] = id; }
    }
    place(p, id, target) {
      if (!this.state.selected[p]?.includes(id) || !Number.isInteger(target) || target < 0 || target >= 5) throw new Error('INVALID_PLACEMENT');
      const slots = this.state.slots[p], old = slots.indexOf(id);
      if (old >= 0) { slots.splice(old, 1); slots.splice(target, 0, id); }
      else slots[target] = id;
    }
    unplace(p, index) { this.state.slots[p][index] = null; }
    edit(p, id, field, value) {
      if (!this.state.selected[p]?.includes(id) || !FIELDS.includes(field)) throw new Error('INVALID_EDIT');
      if (field === 'learning_content_ids' ? !this.validLearning(value) : typeof value !== 'string') throw new Error('INVALID_VALUE');
      const key = `${p}:${id}`, edits = this.state.edits[key] || {};
      if (JSON.stringify(value) === JSON.stringify(this.rows[p][id][field])) delete edits[field]; else edits[field] = value;
      if (Object.keys(edits).length) this.state.edits[key] = edits; else delete this.state.edits[key];
    }
    totals() {
      let selected = 0, placed = 0, incomplete = 0;
      for (const p of this.periods) {
        selected += this.state.selected[p].length;
        for (const id of this.state.slots[p]) if (id) { placed++; if (FIELDS.some(f => !this.row(p, id)[f].trim())) incomplete++; }
      }
      return {selected, placed, incomplete, ready: selected === 20 && placed === 20 && incomplete === 0};
    }
  }
  root.PlayEditorModel = PlanEditor;
  if (typeof module !== 'undefined' && module.exports) module.exports = PlanEditor;
})(globalThis);
