// preload.js — renderer process helpers
const { ipcRenderer } = require('electron');

window.electronAPI = {
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),
  openExternal: (url) => ipcRenderer.send('open-external', url),
  recognizeAudio: (audioBase64) => ipcRenderer.invoke('recognize-audio', audioBase64),
};
