/**
 * Cycling Coach Desktop - Electron 主进程
 *
 * 架构 (production / 装包后):
 *   %LOCALAPPDATA%\Programs\CyclingCoach\
 *     ├─ CyclingCoach.exe                <- Electron 壳
 *     ├─ resources\app\                  <- app.asar (main.cjs, preload.cjs)
 *     ├─ resources\backend\
 *     │   └─ CyclingCoach-backend.exe     <- PyInstaller 单文件后端
 *     ├─ resources\frontend\              <- Vite build 产物
 *     └─ resources\kb_source\             <- 训练百科 (首次启动解压)
 *
 *   %APPDATA%\CyclingCoach\              <- 用户数据 (持久化)
 *     ├─ workspace\                       <- SQLite + 日志
 *     ├─ kb\                              <- 解压后的 KB
 *     └─ logs\                            <- 应用日志
 */
const { app, BrowserWindow, ipcMain, dialog, Menu, shell, Tray, nativeImage } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');
const log = require('electron-log');

const isDev = !app.isPackaged;
const APP_NAME = 'Cycling Coach';
const APP_DISPLAY_NAME = 'Cycling Coach · 公路车 AI 教练';
const BACKEND_PORT = 8765;
const BACKEND_URL = 'http://127.0.0.1:' + BACKEND_PORT;
const BACKEND_HOST = '127.0.0.1';
const BACKEND_HEALTH_TIMEOUT = 60000;

function getCcDir() { return path.join(app.getPath('appData'), 'CyclingCoach'); }
function getKbDir() { return path.join(getCcDir(), 'kb'); }
function getLogDir() { return path.join(getCcDir(), 'logs'); }
function getBackendExe() {
  if (isDev) return path.join(__dirname, '..', '..', 'dist', 'CyclingCoach-backend-dist', 'CyclingCoach-backend');
  const exeName = process.platform === 'win32' ? 'CyclingCoach-backend.exe' : 'CyclingCoach-backend';
  return path.join(process.resourcesPath, 'backend', exeName);
}
function getFrontendDir() {
  if (isDev) return path.join(__dirname, '..', '..', 'cycling_coach', 'static');
  return path.join(process.resourcesPath, 'frontend');
}
function getKbSourceDir() {
  if (isDev) return path.join(__dirname, '..', '..', 'kb_source');
  return path.join(process.resourcesPath, 'kb_source');
}
function getBackendEnv() {
  const env = Object.assign({}, process.env);
  env.IS_DESKTOP = 'true';
  env.STATIC_DIR = getFrontendDir();
  env.WORKSPACE_DIR = getCcDir();
  env.KB_DOWNLOAD_URL = '';
  env.KB_SOURCE_DIR = getKbSourceDir();
  env.BACKEND_PORT = String(BACKEND_PORT);
  env.BACKEND_HOST = BACKEND_HOST;
  env.LOG_LEVEL = process.env.LOG_LEVEL || 'INFO';
  return env;
}
// 跨平台图标: Windows ico, macOS icns, Linux png
function getIconPath() {
  const buildDir = path.join(__dirname, 'build');
  if (process.platform === 'win32') {
    // 优先 ico (NSIS + 任务栏 + 窗口), svg 是矢量 fallback
    return path.join(buildDir, 'icon.ico');
  } else if (process.platform === 'darwin') {
    return path.join(buildDir, 'icon.icns');
  } else {
    return path.join(buildDir, 'icon.png');
  }
}

let backendProcess = null;
let mainWindow = null;
let tray = null;
let isQuitting = false;

function startBackend() {
  return new Promise(function (resolve, reject) {
    const exe = getBackendExe();
    if (!fs.existsSync(exe)) {
      const msg = '后端 binary 不存在: ' + exe + '\n\ndev 模式请先 build: cd 项目根 && pyinstaller apps/desktop/build/pyinstaller-backend.spec --noconfirm --clean';
      log.error(msg);
      reject(new Error(msg));
      return;
    }
    log.info('[backend] starting: ' + exe);
    backendProcess = spawn(exe, [], {
      cwd: getCcDir(),
      env: getBackendEnv(),
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    if (backendProcess.stdout) backendProcess.stdout.on('data', function (d) { log.info('[backend stdout] ' + d.toString().trim()); });
    if (backendProcess.stderr) backendProcess.stderr.on('data', function (d) { log.warn('[backend stderr] ' + d.toString().trim()); });
    backendProcess.on('error', function (err) { log.error('[backend] spawn error: ' + err); reject(err); });
    backendProcess.on('exit', function (code, sig) {
      log.info('[backend] exited code=' + code + ' sig=' + sig);
      backendProcess = null;
      if (!isQuitting && mainWindow) {
        dialog.showErrorBox(APP_NAME, '后端进程退出 (code=' + code + ').\n\n日志: ' + path.join(getLogDir(), 'backend.log'));
        app.quit();
      }
    });
    waitForBackend().then(resolve).catch(reject);
  });
}

function waitForBackend(timeoutMs) {
  if (!timeoutMs) timeoutMs = BACKEND_HEALTH_TIMEOUT;
  const start = Date.now();
  return new Promise(function (resolve, reject) {
    const tryOnce = function () {
      const req = http.get(BACKEND_URL + '/api/kb/stats', function (res) {
        if (res.statusCode === 200) { resolve(); return; }
        retry();
      });
      req.on('error', retry);
      req.setTimeout(2000, function () { req.destroy(); retry(); });
    };
    const retry = function () {
      if (Date.now() - start > timeoutMs) {
        reject(new Error('后端启动超时 (' + (timeoutMs/1000) + 's) — 检查端口占用'));
        return;
      }
      setTimeout(tryOnce, 500);
    };
    tryOnce();
  });
}

function stopBackend() {
  if (!backendProcess) return;
  log.info('[backend] stopping...');
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(backendProcess.pid), '/f', '/t'], { windowsHide: true });
  } else {
    try { backendProcess.kill('SIGTERM'); } catch (_) {}
    setTimeout(function () {
      if (backendProcess) { try { backendProcess.kill('SIGKILL'); } catch (_) {} }
    }, 3000);
  }
  backendProcess = null;
}

function ensureUserDirs() {
  for (const d of [getCcDir(), getKbDir(), getLogDir()]) fs.mkdirSync(d, { recursive: true });
}

function ensureKbInstalled() {
  const installed = path.join(getKbDir(), 'extracted');
  if (fs.existsSync(path.join(installed, 'markdown'))) return;
  const src = getKbSourceDir();
  if (!fs.existsSync(src)) { log.warn('[kb] KB 源不存在: ' + src + ', 跳过'); return; }
  log.info('[kb] 首次启动, 复制训练百科到 ' + getKbDir() + '/extracted ...');
  copyDir(src, installed);
  log.info('[kb] 训练百科已就绪');
}

function copyDir(src, dest) {
  if (fs.statSync(src).isDirectory()) {
    fs.mkdirSync(dest, { recursive: true });
    for (const entry of fs.readdirSync(src)) copyDir(path.join(src, entry), path.join(dest, entry));
  } else {
    fs.copyFileSync(src, dest);
  }
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: APP_DISPLAY_NAME,
    backgroundColor: '#f5f7fa',
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
    icon: getIconPath(),
  });
  mainWindow.loadURL(BACKEND_URL);
  mainWindow.once('ready-to-show', function () { mainWindow.show(); });
  mainWindow.webContents.setWindowOpenHandler(function (e) {
    if (e.url.startsWith('http')) shell.openExternal(e.url);
    return { action: 'deny' };
  });
  mainWindow.on('close', function (e) {
    if (!isQuitting) { e.preventDefault(); mainWindow.hide(); showTrayNotification(); }
  });
  mainWindow.on('closed', function () { mainWindow = null; });
}

function createTray() {
  if (tray) return;
  const icon = nativeImage.createFromPath(getIconPath());
  tray = new Tray(icon);
  tray.setToolTip(APP_NAME);
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '打开 Cycling Coach', click: function () { if (mainWindow) { mainWindow.show(); mainWindow.focus(); } } },
    { label: '打开数据目录', click: function () { shell.openPath(getCcDir()); } },
    { type: 'separator' },
    { label: '退出', click: function () { isQuitting = true; app.quit(); } },
  ]));
  tray.on('double-click', function () { if (mainWindow) { mainWindow.show(); mainWindow.focus(); } });
}

function showTrayNotification() {
  if (process.platform === 'win32' && tray) {
    tray.displayBalloon({
      title: APP_NAME,
      content: 'Cycling Coach 仍在后台运行. 双击托盘图标可重新打开主窗口.',
    });
  }
}

function buildMenu() {
  const isMac = process.platform === 'darwin';
  const template = [
  ].concat(isMac ? [{ role: 'appMenu' }] : []).concat([
    {
      label: '文件',
      submenu: [
        { label: '导入 FIT/TCX/GPX...', accelerator: 'CmdOrCtrl+I', click: function () { if (mainWindow) mainWindow.webContents.send('nav:import'); } },
        { label: '打开数据目录', click: function () { shell.openPath(getCcDir()); } },
        { type: 'separator' },
        isMac ? { role: 'close' } : { label: '退出', accelerator: 'CmdOrCtrl+Q', click: function () { isQuitting = true; app.quit(); } },
      ],
    },
    { label: '视图', submenu: [{ role: 'reload' }, { role: 'toggleDevTools' }, { type: 'separator' }, { role: 'togglefullscreen' }] },
    {
      label: '帮助',
      submenu: [
        {
          label: '关于 Cycling Coach',
          click: function () {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: '关于',
              message: APP_DISPLAY_NAME,
              detail: 'v' + app.getVersion() + '\n\n公路自行车 AI 教练\n潘震(公路车教练) 训练百科\n\n本地优先 · 开源免费\n\n数据目录: ' + getCcDir(),
            });
          },
        },
        { label: '打开日志目录', click: function () { shell.openPath(getLogDir()); } },
      ],
    },
  ]);
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function setupIpc() {
  ipcMain.handle('app:version', function () { return app.getVersion(); });
  ipcMain.handle('app:userDataDir', function () { return getCcDir(); });
  ipcMain.handle('app:openDataDir', function () { return shell.openPath(getCcDir()); });
  ipcMain.handle('app:openLogDir', function () { return shell.openPath(getLogDir()); });
  ipcMain.handle('app:showImport', function () { if (mainWindow) mainWindow.webContents.send('nav:import'); });
  ipcMain.handle('app:restartBackend', async function () { stopBackend(); await startBackend(); return true; });
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', function () {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });

  app.on('ready', async function () {
    try {
      log.info('='.repeat(50));
      log.info(APP_DISPLAY_NAME + ' v' + app.getVersion() + ' starting...');
      log.info('User data: ' + getCcDir());
      log.info('Mode: ' + (isDev ? 'development' : 'production'));

      ensureUserDirs();
      log.transports.file.resolvePath = function () { return path.join(getLogDir(), 'electron.log'); };
      ensureKbInstalled();
      await startBackend();

      buildMenu();
      setupIpc();
      createMainWindow();
      createTray();
      log.info(APP_NAME + ' ready');
    } catch (e) {
      log.error('启动失败: ' + e.message + '\n' + e.stack);
      dialog.showErrorBox(APP_NAME, '启动失败: ' + e.message + '\n\n详细日志: ' + path.join(getLogDir(), 'electron.log'));
      app.quit();
    }
  });
}

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') { isQuitting = true; app.quit(); }
});
app.on('activate', function () { if (!mainWindow) createMainWindow(); else mainWindow.show(); });
app.on('before-quit', function () { isQuitting = true; stopBackend(); });
app.on('will-quit', function () { stopBackend(); });

process.on('uncaughtException', function (e) { log.error('uncaughtException:', e); });
process.on('unhandledRejection', function (e) { log.error('unhandledRejection:', e); });
