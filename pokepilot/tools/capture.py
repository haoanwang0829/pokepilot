"""
画面采集层 - 从 OBS 虚拟摄像机或采集卡读取 Switch 画面
"""

import cv2
import time
from pathlib import Path


def list_video_devices(max_index: int = 10) -> list[int]:
    """扫描可用的视频设备，返回可用设备的索引列表"""
    available = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                available.append(i)
        cap.release()
    return available


class ScreenCapture:
    """
    从视频设备（OBS 虚拟摄像机 / 采集卡）持续采集画面。

    使用方式：
        cap = ScreenCapture(device_index=1)
        cap.start()
        frame = cap.read()   # 获取最新帧 (BGR numpy array, shape: H×W×3)
        cap.stop()
    """

    # Switch 原生分辨率
    SWITCH_W = 1920
    SWITCH_H = 1080

    def __init__(self, device_index: int = 0):
        self.device_index = device_index
        self._cap: cv2.VideoCapture | None = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """打开设备，配置分辨率"""
        self._cap = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"无法打开设备 {self.device_index}。"
                "请确认 OBS 虚拟摄像机已启动，或采集卡驱动正常。"
            )

        # 尝试设置 1080p（采集卡/OBS 不一定响应，但尽量请求）
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.SWITCH_W)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.SWITCH_H)

        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[Capture] 设备 {self.device_index} 已打开，分辨率 {actual_w}×{actual_h}")

    def stop(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

    # ------------------------------------------------------------------
    # 读帧
    # ------------------------------------------------------------------

    def read(self) -> cv2.typing.MatLike | None:
        """返回最新一帧（BGR），读取失败返回 None"""
        if not self._cap:
            raise RuntimeError("请先调用 start()")
        ret, frame = self._cap.read()
        return frame if ret else None

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def save_frame(self, frame, path: str | Path) -> None:
        """保存单帧到文件，用于后续标注布局"""
        cv2.imwrite(str(path), frame)
        print(f"[Capture] 已保存截图: {path}")


# ------------------------------------------------------------------
# 独立运行：实时预览 + 按 S 截图 + 按 Q 退出
# ------------------------------------------------------------------

def _preview(device_index: int) -> None:
    screenshots_dir = Path("screenshots")
    screenshots_dir.mkdir(exist_ok=True)

    cap = ScreenCapture(device_index)
    cap.start()

    print("预览中 —— 按 S 截图，按 Q 退出")
    while True:
        frame = cap.read()
        if frame is None:
            print("[Capture] 读帧失败，重试...")
            time.sleep(0.1)
            continue

        # 如果画面超过 1280 宽，缩小预览窗口（不影响保存的截图）
        display = cv2.resize(frame, (1280, 720)) if frame.shape[1] > 1280 else frame
        cv2.imshow("PokePilot - Capture Preview", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("s"):
            ts = time.strftime("%Y%m%d_%H%M%S")
            save_path = screenshots_dir / f"frame_{ts}.png"
            cap.save_frame(frame, save_path)  # 保存原始分辨率

    cap.stop()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PokePilot 画面采集层")
    parser.add_argument(
        "--list", action="store_true", help="列出所有可用视频设备"
    )
    parser.add_argument(
        "--device", type=int, default=None, help="指定设备索引（默认自动选第一个可用）"
    )
    args = parser.parse_args()

    if args.list:
        print("扫描视频设备...")
        devices = list_video_devices()
        if devices:
            print(f"找到设备索引: {devices}")
        else:
            print("未找到任何视频设备")
    else:
        if args.device is not None:
            idx = args.device
        else:
            print("未指定设备，自动扫描...")
            devices = list_video_devices()
            if not devices:
                print("未找到任何视频设备，请检查 OBS 虚拟摄像机是否已启动")
                raise SystemExit(1)
            idx = devices[0]
            print(f"自动选择设备 {idx}")
        _preview(idx)
