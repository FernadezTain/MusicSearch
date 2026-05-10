const { app, BrowserWindow, ipcMain, shell } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 480,
    height: 720,
    minWidth: 420,
    minHeight: 600,
    frame: false,
    transparent: false,
    backgroundColor: '#0a0a0f',
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      enableRemoteModule: true,
    },
    icon: path.join(__dirname, '../assets/icon.png'),
    titleBarStyle: 'hidden',
    resizable: true,
  });

  mainWindow.loadFile(path.join(__dirname, 'index.html'));

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

// Window controls
ipcMain.on('window-minimize', () => mainWindow.minimize());
ipcMain.on('window-maximize', () => {
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
});
ipcMain.on('window-close', () => mainWindow.close());

// Open external links
ipcMain.on('open-external', (event, url) => {
  shell.openExternal(url);
});

// FernieID deeplink: trackr://fernie?token=...
app.setAsDefaultProtocolClient('trackr');
app.on('open-url', (event, url) => {
  event.preventDefault();
  try {
    const u = new URL(url);
    if (u.hostname === 'fernie') {
      const token = u.searchParams.get('token');
      if (token && mainWindow) {
        mainWindow.webContents.executeJavaScript(`
          fetch('https://ferniex-id.vercel.app/api/me', {
            headers: { Authorization: 'Bearer ${token}' }
          })
          .then(r => r.json())
          .then(user => {
            fernieUser = user;
            localStorage.setItem('fernie_user', JSON.stringify(user));
            renderFernieProfile();
            switchTab('profile');
          })
          .catch(console.error);
        `);
      }
    }
  } catch(e) {}
});

// ShazamIO recognition via Python
ipcMain.handle('recognize-audio', async (event, audioBase64) => {
  return new Promise((resolve, reject) => {
    // Сохраняем base64-аудио во временный файл
    const tmpPath = path.join(os.tmpdir(), `trackr_${Date.now()}.webm`);
    fs.writeFileSync(tmpPath, Buffer.from(audioBase64, 'base64'));

    const py = spawn('python3', [
      path.join(__dirname, 'shazam_worker.py'),
      tmpPath
    ], {
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' }
    });

    let stdout = '';
    let stderr = '';

    py.stdout.on('data', d => { stdout += d.toString(); });
    py.stderr.on('data', d => {
      stderr += d.toString();
      mainWindow.webContents.executeJavaScript(`console.log("PY STDERR:", ${JSON.stringify(d.toString())})`);
    });

    py.on('close', (code) => {
      mainWindow.webContents.executeJavaScript(`console.log("PY EXIT:", ${code}, "STDOUT:", ${JSON.stringify(stdout)}, "STDERR:", ${JSON.stringify(stderr)})`);
      fs.unlink(tmpPath, () => {});
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(new Error(stderr || stdout || 'Ошибка Python-воркера'));
      }
    });
  });
});