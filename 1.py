# Assumption:
# - Our drain is 40cm tall
# Install ttkbootstrap - sudo /usr/bin/python3 -m pip install ttkbootstrap

import RPi.GPIO as GPIO
import time
import tkinter as tk
import requests
import threading
from ttkbootstrap import Style
from ttkbootstrap.constants import *
from datetime import datetime
from picamera import PiCamera
from tkinter import ttk

# Initialize PiCamera
try:
    camera = PiCamera()
    camera.resolution = (1920, 1080)
    print("Camera initialized successfully")
except Exception as e:
    print(f"Camera Error: {e}")

# Thinkspeak setup
THINGSPEAK_API_KEY = '82IUHYX3J93870M5'
THINGSPEAK_URL = 'https://api.thingspeak.com/update?api_key=82IUHYX3J93870M5&field1=0'

# Telegram setup
TELEGRAM_BOT_TOKEN = '7817255218:AAE3yKo202jecA-DUkGM-XUS3J6P7ad4_gQ'
TELEGRAM_CHAT_ID = '5145469528'
TELEGRAM_URL = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'

# GPIO setup
TRIG = 25
ECHO = 27
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

# Alert flags and LED control
alert_sent_danger = False
alert_sent_warning = False
blink_active = False
blink_state = False
current_alert = None
last_alert_time = None

def measure_distance():
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    while GPIO.input(ECHO) == 0:
        pulse_start = time.time()
    while GPIO.input(ECHO) == 1:
        pulse_end = time.time()

    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150
    return round(distance, 2)

def capture_image():
    try:
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"alert_{timestamp}.jpg"
        camera.capture(filename)
        return filename
    except Exception as e:
        print("Camera Error:", e)
        return None

def send_telegram_alert(message):
    try:
        requests.post(TELEGRAM_URL, data={'chat_id': TELEGRAM_CHAT_ID, 'text': message})
    except Exception as e:
        print("Telegram Error:", e)

def send_telegram_photo(photo_path, caption="Flood Alert Image"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as f:
            files = {'photo': ('image.jpg', f.read())}
            requests.post(url, files=files, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption})
    except Exception as e:
        print("Telegram Photo Error:", e)

# GUI setup
style = Style(theme='darkly')
root = style.master
root.title("Flood Level Monitor")
root.geometry("800x600")

# Title
title = tk.Label(root, text="Flood Level Detection", font=("Helvetica", 18), fg="white", bg="#222")
title.pack(pady=10)

# Distance display
distance_label = tk.Label(root, text="Distance: -- cm", font=("Helvetica", 16), fg="white", bg="#222")
distance_label.pack(pady=10)

# Main frame
main_frame = ttk.Frame(root)
main_frame.pack(pady=20, padx=20, fill='both', expand=True)

# Progress bar
progress_frame = ttk.Frame(main_frame)
progress_frame.pack(pady=10)
percent_label = ttk.Label(progress_frame, text="0%", font=("Helvetica", 12))
percent_label.pack()

progress = ttk.Progressbar(
    progress_frame,
    orient=HORIZONTAL,
    length=500,
    mode='determinate',
    bootstyle="info-striped",
    maximum=40
)
progress.pack()

marker_frame = ttk.Frame(progress_frame)
marker_frame.pack(fill='x')
ttk.Label(marker_frame, text="25cm", foreground="orange").pack(side='left', padx=115)
ttk.Label(marker_frame, text="10cm", foreground="red").pack(side='right', padx=115)

# LED Control
status_led = tk.Canvas(main_frame, width=50, height=50, bg="#222", highlightthickness=0)
status_led.pack(pady=10)
led_circle = status_led.create_oval(10, 10, 40, 40, fill="gray", outline="white")

status_label = ttk.Label(main_frame, text="System Offline", font=("Helvetica", 14))
status_label.pack()

def update_led(state):
    colors = {
        "safe": ("green", "✅ SAFE"),
        "warning": ("orange", "⚠️ WARNING"), 
        "danger": ("red", "❗ DANGER"),
        "off": ("gray", "System Offline")
    }
    color, text = colors[state]
    status_led.itemconfig(led_circle, fill=color)
    status_label.config(text=text, foreground=color)

def blink_led():
    global blink_state
    if blink_active:
        blink_state = not blink_state
        if current_alert == "danger":
            status_led.itemconfig(led_circle, fill="#FF0000" if blink_state else "#400000")
            root.after(250, blink_led)
        elif current_alert == "warning":
            status_led.itemconfig(led_circle, fill="#FFA500" if blink_state else "#805000")
            root.after(500, blink_led)

def stop_blinking():
    global blink_active
    blink_active = False
    update_led("safe")

# Time since last alert
time_label = ttk.Label(main_frame, text="Last alert: Never")
time_label.pack()

def handle_alert(dist, time_str, level):
    message = f"{level}: {dist} cm"
    photo_file = capture_image()
    if photo_file:
        send_telegram_photo(photo_file, caption=f"{message} at {time_str}")
    else:
        send_telegram_alert(f"{message} at {time_str}")

def update_reading():
    global alert_sent_danger, alert_sent_warning, blink_active, current_alert, last_alert_time

    try:
        dist = measure_distance()
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        
        # Update displays
        clamped_dist = max(0, min(dist, 40))
        fill_level = 40 - clamped_dist
        percent = int((fill_level / 40) * 100)
        distance_label.config(text=f"Distance: {dist} cm")
        percent_label.config(text=f"{percent}%")
        progress['value'] = fill_level

        # Alert logic
        if clamped_dist < 10:  # DANGER
            progress.configure(bootstyle="danger-striped")
            if current_alert != "danger":
                current_alert = "danger"
                blink_active = True
                blink_led()
                update_led("danger")
                if not alert_sent_danger:
                    last_alert_time = time.time()
                    send_telegram_alert(f"Flood Alert! Water: {dist}cm")
                    threading.Thread(target=handle_alert, args=(dist, time_str, "DANGER")).start()
                    alert_sent_danger = True
                    alert_sent_warning = False
                    
        elif clamped_dist < 25:  # WARNING
            progress.configure(bootstyle="warning-striped")
            if current_alert != "warning":
                current_alert = "warning"
                blink_active = True
                blink_led()
                update_led("warning")
                if not alert_sent_warning:
                    last_alert_time = time.time()
                    send_telegram_alert(f"Flood Warning! Water: {dist}cm")
                    threading.Thread(target=handle_alert, args=(dist, time_str, "WARNING")).start()
                    alert_sent_warning = True
                alert_sent_danger = False
                
        else:  # SAFE
            progress.configure(bootstyle="success-striped")
            if current_alert != "safe":
                current_alert = "safe"
                stop_blinking()
                update_led("safe")
                alert_sent_danger = False
                alert_sent_warning = False

        # Update alert time
        if last_alert_time:
            seconds = int(time.time() - last_alert_time)
            time_label.config(text=f"Last alert: {seconds}s ago")

        # Send to Thingspeak
        try:
            requests.post(THINGSPEAK_URL, params={
                'api_key': THINGSPEAK_API_KEY,
                'field3': dist
            })
        except Exception as e:
            print("ThingSpeak Error:", e)

    except Exception as e:
        stop_blinking()
        update_led("off")
        distance_label.config(text="Error reading sensor")

    root.after(2000, update_reading)

# Quit function
def quit_app():
    GPIO.cleanup()
    root.destroy()

quit_button = tk.Button(root, text="Quit", command=quit_app, bg="#555", fg="white")
quit_button.pack(pady=20)

# Start system
root.after(1000, update_reading)
root.mainloop()
GPIO.cleanup()
