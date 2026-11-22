import { JSDOM } from 'jsdom';

const dom = new JSDOM('', { url: 'http://localhost' });
globalThis.localStorage = dom.window.localStorage;
