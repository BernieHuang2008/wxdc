import adbutils
import time
import cv2
import numpy as np
import os
from PIL import Image
import pytesseract
from pytesseract import Output

from yadb import YadbClient

adb = None
device = None
yadb = None

def isconnected():
    global adb, device, yadb
    return adb is not None and device is not None and yadb is not None

def connect():
    if isconnected():
        return
    
    global adb, device, yadb
    adb = adbutils.AdbClient()
    device = adb.device(serial="WJX7N17731000362")
    yadb = YadbClient(device)

def get_curr():
    app_info = device.app_current()
    return app_info

def back_to_home():
    device.shell('input keyevent KEYCODE_APP_SWITCH')
    device.shell('input tap 550 1700')

def open_wechat():
    device.click(120, 200)


def open_tongxunlu():
    device.click(400, 1800)

def open_tongxunlu_tags():
    device.click(120, 850)

def input_chinese(text):
    """
    通过 ADBKeyboard 输入中文 (基于 adbutils)
    """
    escaped_text = text.replace('"', '\\"')
    cmd = f'am broadcast -a ADB_INPUT_TEXT --es msg "{escaped_text}"'
    
    result = device.shell2(cmd)
    return result

def find_template(image: np.ndarray, template_path_or_dir: str, 
                  method=cv2.TM_CCOEFF_NORMED, threshold=0.0):
    """
    在图像中查找模板（支持单文件或目录下所有图片），返回最佳匹配的位置和置信度。
    
    参数:
        image:          numpy array 格式的图像 (BGR 或灰度)
        template_path_or_dir:  模板文件路径 或 包含模板图片的目录路径
        method:         匹配方法，默认 cv2.TM_CCOEFF_NORMED
        threshold:      置信度阈值，低于此值的结果将被忽略（默认0表示全部接受）
    
    返回:
        (best_loc, best_conf) 或 (None, None)
            best_loc:   (x, y) 左上角坐标
            best_conf:  匹配置信度 (0~1)
    """
    # 如果输入是彩色图，转为灰度图（匹配更高效）
    if len(image.shape) == 3:
        img_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = image

    # 获取所有模板文件的路径
    if os.path.isdir(template_path_or_dir):
        # 目录：收集所有常见图片格式文件
        valid_ext = ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff')
        template_files = [
            os.path.join(template_path_or_dir, f) 
            for f in os.listdir(template_path_or_dir) 
            if f.lower().endswith(valid_ext)
        ]
        if not template_files:
            print(f"目录 {template_path_or_dir} 中没有图片文件")
            return None, None
    elif os.path.isfile(template_path_or_dir):
        template_files = [template_path_or_dir]
    else:
        print(f"路径不存在: {template_path_or_dir}")
        return None, None

    best_loc = None
    best_conf = -1.0

    for tmp_path in template_files:
        # 读取模板（灰度）
        template = cv2.imread(tmp_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            print(f"无法读取模板文件: {tmp_path}")
            continue

        # 检查模板尺寸是否小于大图
        if template.shape[0] > img_gray.shape[0] or template.shape[1] > img_gray.shape[1]:
            print(f"模板 {os.path.basename(tmp_path)} 尺寸大于原图，跳过")
            continue

        # 执行模板匹配
        result = cv2.matchTemplate(img_gray, template, method)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        # 更新最佳结果
        if max_val > best_conf and max_val >= threshold:
            best_conf = max_val
            best_loc = max_loc  # 注意：max_loc 是左上角坐标

    if best_loc is None:
        return None, None
    return best_loc, best_conf

def img_threshold(img, threshold=50):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary_fixed = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
    return binary_fixed

def ocr(img):
    data = pytesseract.image_to_data(img, output_type=Output.DICT, lang='chi_sim+eng')
    return data


def wait_until(activity, timeuot=5):
    """
    等待直到当前应用的 activity 与指定 activity 匹配。
    
    参数:
        activity: 目标 activity 名称（字符串）
    """
    cnt = 0
    while cnt < timeuot:
        current_activity = device.app_current().activity
        if current_activity == activity:
            break
        time.sleep(0.25)  # 每隔 0.25 秒检查一次
        cnt += 0.25
    else:
        raise TimeoutError(f"等待 {timeuot} 秒后仍未匹配到 activity: {activity}, 当前 activity: {current_activity}")



def navigate_to_chat(target_ugroup, target_user):
    if device.app_current().activity != "com.tencent.mm.ui.LauncherUI":
        back_to_home()
        wait_until("com.huawei.android.launcher.unihome.UniHomeLauncher")
        open_wechat()
        wait_until("com.tencent.mm.ui.LauncherUI")

    
    for _ in range(3):
        open_tongxunlu()
        time.sleep(0.3)
        if find_template(np.array(device.screenshot())[122:181, 456:623], "/app/wxsrc/tongxunlu.png", threshold=0.8)[0] is not None:
            break
    else:
        return "Abort: 未找到通讯录入口"

    open_tongxunlu_tags()
    wait_until("com.tencent.mm.plugin.label.ui.ContactLabelManagerUI")

    # # ensure 通讯录 page is open
    # screenshot = np.array(device.screenshot())
    # if find_template(screenshot[120:180, 400:680], "/app/wxsrc/tongxunlutag.png", threshold=0.8)[0] is None:
    #     return "Abort: 未找到通讯录标签"

    # find target group
    for _ in range(3):  # TODO: [conf] max attempts depending on the list length
        data = ocr(img_threshold(np.array(device.screenshot())[220:1740], 50))
        if target_ugroup in data['text']:
            i = data['text'].index(target_ugroup)
            (x, y, w, h) = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
            if y < 700:
                device.click(x, y+240)  # +20 for border situations
            else:
                device.click(x, y+220)
            break
        else:
            yadb.swipe(400, 1700, 400, 300, 400)

    wait_until("com.tencent.mm.ui.mvvm.MvvmContactListUI")

    # find target user
    for _ in range(3):  # TODO: [conf] max attempts depending on the list length
        data = ocr(img_threshold(np.array(device.screenshot())[220:1740, 220:1040], 50))
        if target_user in data['text']:
            i = data['text'].index(target_user)
            (x, y, w, h) = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
            if y < 700:
                device.click(x, y+240)  # +20 for border situations
            else:
                device.click(x, y+220)
            break
        else:
            yadb.swipe(400, 1700, 400, 300, 400)

    wait_until("com.tencent.mm.plugin.profile.ui.ContactInfoUI")

    pos = find_template(np.array(device.screenshot())[1000:], "/app/wxsrc/faxiaoxi.png", threshold=0.8)[0]
    device.click(pos[0], pos[1]+1000)

    try:
        wait_until("com.tencent.mm.ui.chatting.ChattingUI")
    except TimeoutError:
        if device.app_current().activity != "com.tencent.mm.plugin.profile.ui.ContactInfoUI":
            device.keyevent("KEYCODE_BACK")
        time.sleep(5)
        pos = find_template(np.array(device.screenshot())[1000:], "/app/wxsrc/faxiaoxi.png", threshold=0.8)[0]
        device.click(pos[0], pos[1]+1000)
        wait_until("com.tencent.mm.plugin.profile.ui.ContactInfoUI")

    # ensure the chat user
    data = ocr(np.array(device.screenshot())[120:180, 320:750])
    if target_user in data['text']:
        return True
    else:
        return False

    # ===== NAVIGATION COMPLETE. =====

def navigate_to_tongxunlu_from_chat():
    wait_until("com.tencent.mm.ui.chatting.ChattingUI")
    device.keyevent("KEYCODE_BACK")
    try:
        wait_until("com.tencent.mm.plugin.profile.ui.ContactInfoUI", timeout=2)
    except TimeoutError:
        if device.app_current().activity == "com.tencent.mm.ui.chatting.ChattingUI":
            device.keyevent("KEYCODE_BACK")
            wait_until("com.tencent.mm.plugin.profile.ui.ContactInfoUI", timeout=2)

    device.keyevent("KEYCODE_BACK")
    wait_until("com.tencent.mm.ui.mvvm.MvvmContactListUI", timeout=2)
    device.keyevent("KEYCODE_BACK")
    wait_until("com.tencent.mm.plugin.label.ui.ContactLabelManagerUI", timeout=2)
    device.keyevent("KEYCODE_BACK")
    wait_until("com.tencent.mm.ui.LauncherUI", timeout=2)

def send_text(text):
    device.click(450, 1833)
    input_chinese(text)
    device.click(987, 1767)
    device.keyevent("KEYCODE_BACK")

def send_image(image_path):
    device.click(1010, 1833)
    device.push(image_path, "/storage/emulated/0/Pictures/to_send.png")
    time.sleep(0.5)

    if find_template(np.array(device.screenshot())[1291:1363, 128:220], "/app/wxsrc/xiangce.png", threshold=0.8)[0] is not None:
        device.click(200, 1300)
        wait_until("com.tencent.mm.plugin.gallery.ui.AlbumPreviewUI")
        device.click(211, 285)
        device.click(937, 1842)

        return True
    else:
        return False

if __name__ == "__main__":
    connect()
    navigate_to_chat("group-1", "user-1")
    send_text("你好，黄瓜！\n换行\n\n")
    send_image("/app/wxsrc/xiangce.png")
    navigate_to_tongxunlu_from_chat()
