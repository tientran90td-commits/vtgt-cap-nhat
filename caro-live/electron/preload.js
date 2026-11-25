'use strict';
const { contextBridge, ipcRenderer } = require('electron');
const call = (name) => (...a) => ipcRenderer.invoke(name, ...a);
contextBridge.exposeInMainWorld('caro', {
  state: call('state'),
  start: call('start'),
  stop: call('stop'),
  openLive: call('openLive'),
  openPanel: call('openPanel'),
  importOld: call('importOld'),
  openFolder: call('openFolder'),
  remoteConfig: call('remoteConfig'),
  on: (ch, fn) => ipcRenderer.on(ch, (_e, d) => fn(d)),
});
