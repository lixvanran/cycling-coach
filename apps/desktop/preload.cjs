/**
 * Preload - 安全 IPC 桥
 * 暴露最小 API 给前端 (contextIsolation: true)
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  getVersion: () => ipcRenderer.invoke('app:version'),
  getUserDataDir: () => ipcRenderer.invoke('app:userDataDir'),
  openDataDir: () => ipcRenderer.invoke('app:openDataDir'),
  openLogDir: () => ipcRenderer.invoke('app:openLogDir'),
  showImport: () => ipcRenderer.invoke('app:showImport'),
  restartBackend: () => ipcRenderer.invoke('app:restartBackend'),
  // 主进程 -> 渲染进程 事件
  onNavImport: (cb) => ipcRenderer.on('nav:import', () => cb()),
});
