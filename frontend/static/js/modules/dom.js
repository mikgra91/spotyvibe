/**
 * dom.js — Lightweight DOM query helpers to reduce getElementById/querySelector noise.
 *
 * Usage:
 *   import { el, qs, qsa } from './dom.js';
 *   el('myId')            // document.getElementById('myId')
 *   qs('.my-class')       // document.querySelector('.my-class')
 *   qsa('.items')         // document.querySelectorAll('.items')
 */

/** @param {string} id @returns {HTMLElement|null} */
export const el = (id) => document.getElementById(id);

/** @param {string} sel @param {Element} [root=document] @returns {Element|null} */
export const qs = (sel, root = document) => root.querySelector(sel);

/** @param {string} sel @param {Element} [root=document] @returns {NodeListOf<Element>} */
export const qsa = (sel, root = document) => root.querySelectorAll(sel);

