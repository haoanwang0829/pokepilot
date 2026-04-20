let stream = null;
const API_BASE = "http://localhost:8765";

// ==================== 菜单管理 ====================
function toggleMenu(menuId) {
    const menu = document.getElementById(menuId);
    const isActive = menu.classList.contains('active');

    // 关闭所有菜单
    document.querySelectorAll('.menu-item.active').forEach(m => {
        m.classList.remove('active');
    });

    // 如果不是当前菜单的状态，打开
    if (!isActive) {
        menu.classList.add('active');
    }
}

// 点击外部关闭菜单
document.addEventListener('click', (e) => {
    if (!e.target.closest('.menu-item')) {
        document.querySelectorAll('.menu-item.active').forEach(m => {
            m.classList.remove('active');
        });
    }
});

// ==================== 设备管理 ====================
let currentDeviceId = null;
let currentAudioDeviceId = null;

async function loadDevices() {
    setLog('加载设备列表...');
    try {
        // 先请求权限，否则 label 为空
        await navigator.mediaDevices.getUserMedia({ video: true, audio: true }).then(s => s.getTracks().forEach(t => t.stop()));
    } catch (_) {}

    const devices = await navigator.mediaDevices.enumerateDevices();
    const videoDevices = devices.filter(d => d.kind === 'videoinput');
    const audioDevices = devices.filter(d => d.kind === 'audioinput');
    const submenu = document.getElementById('device-submenu');
    submenu.innerHTML = '';

    if (videoDevices.length === 0) {
        submenu.innerHTML = '<div class="dropdown-item">未找到设备</div>';
        setInfo('未找到任何视频设备');
        return;
    }

    videoDevices.forEach(d => {
        const item = document.createElement('div');
        item.className = 'dropdown-item';
        item.textContent = d.label || `摄像头 ${d.deviceId.slice(0, 8)}`;
        item.onclick = () => selectDevice(d.deviceId, item.textContent);
        submenu.appendChild(item);
    });

    // 填充音频设备列表
    const audioSubmenu = document.getElementById('audio-submenu');
    audioSubmenu.innerHTML = '';
    if (audioDevices.length === 0) {
        audioSubmenu.innerHTML = '<div class="dropdown-item">未找到音频设备</div>';
    } else {
        audioDevices.forEach(d => {
            const item = document.createElement('div');
            item.className = 'dropdown-item';
            item.textContent = d.label || `麦克风 ${d.deviceId.slice(0, 8)}`;
            item.onclick = () => selectAudioDevice(d.deviceId, item.textContent);
            audioSubmenu.appendChild(item);
        });
    }

    setInfo(`找到 ${videoDevices.length} 个视频设备，${audioDevices.length} 个音频设备`);
    setLog(`已加载 ${videoDevices.length} 个设备`);
}

function selectDevice(deviceId, label) {
    currentDeviceId = deviceId;
    setInfo(`已选择视频: ${label}`);
    setLog(`已选择视频: ${label}`);
}

function selectAudioDevice(deviceId, label) {
    currentAudioDeviceId = deviceId;
    setInfo(`已选择音频: ${label}`);
    setLog(`已选择音频: ${label}`);
}

async function startCapture() {
    if (!currentDeviceId) {
        alert('请先选择设备');
        return;
    }
    const deviceId = currentDeviceId;

    stopCapture();
    setLog('连接中...');

    try {
        const constraints = {
            video: { deviceId: { exact: deviceId }, width: { ideal: 1920 }, height: { ideal: 1080 } }
        };

        // 如果选中了音频设备，就加上
        if (currentAudioDeviceId) {
            constraints.audio = {
                deviceId: { exact: currentAudioDeviceId },
                sampleRate: { ideal: 48000 },
                echoCancellation: false,
                noiseSuppression: false,
                autoGainControl: false
            };
        }

        stream = await navigator.mediaDevices.getUserMedia(constraints);
        document.getElementById('video').srcObject = stream;
        setStatus('已连接', 'connected');
        setLog('视频流已启动');
        document.getElementById('btn-start').disabled = true;
        document.getElementById('btn-stop').disabled = false;
    } catch (err) {
        setStatus(`错误: ${err.message}`, 'error');
        setLog(`连接失败: ${err.message}`);
    }
}

function stopCapture() {
    if (stream) {
        stream.getTracks().forEach(t => t.stop());
        stream = null;
    }
    document.getElementById('video').srcObject = null;
    setStatus('已停止', '');
    setInfo('视频已停止');
    setLog('已停止');
    document.getElementById('btn-start').disabled = false;
    document.getElementById('btn-stop').disabled = true;
}

// ==================== 队伍操作 ====================
async function captureScreen(stage) {
    const video = document.getElementById('video');
    if (!video.srcObject) {
        setLog('错误: 未连接视频源');
        return;
    }

    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);

    setLog(`正在保存 ${stage === 'moves' ? '页面1(Moves)' : '页面2(Stats)'}...`);

    try {
        const blob = await new Promise(resolve => canvas.toBlob(resolve));
        const formData = new FormData();
        formData.append('image', blob);
        formData.append('type', stage);

        const response = await fetch(`${API_BASE}/api/screenshot`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();
        if (result.success) {
            setLog(`✓ ${stage === 'moves' ? 'Moves页面' : 'Stats页面'} 已保存: ${result.filename}`);
        } else {
            setLog(`✗ 保存失败: ${result.error}`);
        }
    } catch (err) {
        setLog(`✗ 错误: ${err.message}`);
    }
}

function generateTeam() {
    setLog('生成队伍');
    alert('功能开发中: 生成队伍');
}

function loadTeam() {
    setLog('读取队伍');
    alert('功能开发中: 读取队伍');
}

function saveTeam() {
    setLog('写入队伍');
    alert('功能开发中: 写入队伍');
}

// ==================== UI 工具 ====================
function setStatus(msg, cls = '') {
    const el = document.getElementById('status');
    el.textContent = msg;
    el.className = 'menu-status ' + cls;
}

function setInfo(msg) {
    // 设备信息现在显示在日志里
    setLog(msg);
}

function setLog(msg) {
    document.getElementById('info-log').textContent = msg;
}

function logMsg(msg) {
    setLog(msg);
}

function closeAllMenus() {
    document.querySelectorAll('.menu-item').forEach(m => {
        m.classList.remove('active');
    });
}

// ==================== 初始化 ====================
window.addEventListener('load', async () => {
    setLog('初始化...');
    await loadDevices();
});

window.addEventListener('beforeunload', () => {
    if (stream) stopCapture();
});
