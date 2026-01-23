import psutil
import platform
import time
import subprocess
import pyrogram
import motor
import pymongo
from utils import humanbytes, get_readable_time

def get_progress_bar(percentage, segments=12):
    filled = int(percentage / 100 * segments)
    return "⬢" * filled + "⬡" * (segments - filled)

def get_system_stats(bot_uptime):
    # Repository Stats
    try:
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
        commit_date_str = subprocess.check_output(["git", "log", "-1", "--format=%cd", "--date=format:%Y-%m-%d"]).decode().strip()
        commit_timestamp = int(subprocess.check_output(["git", "log", "-1", "--format=%at"]).decode().strip())
        last_commit = subprocess.check_output(["git", "log", "-1", "--format=%s"]).decode().strip()

        age_seconds = int(time.time()) - commit_timestamp
        if age_seconds < 60:
            commit_age = f"{age_seconds} seconds ago"
        elif age_seconds < 3600:
            commit_age = f"{age_seconds // 60} minutes ago"
        elif age_seconds < 86400:
            commit_age = f"{age_seconds // 3600} hours ago"
        else:
            commit_age = f"{age_seconds // 86400} days ago"
    except Exception:
        branch = "N/A"
        commit_date_str = "N/A"
        commit_age = "N/A"
        last_commit = "N/A"

    # OS Stats
    os_dist = platform.system()
    if platform.system() == "Linux":
        try:
            with open("/etc/os-release") as f:
                lines = f.readlines()
                for line in lines:
                    if line.startswith("PRETTY_NAME="):
                        os_dist = line.split("=")[1].strip().strip('"')
                        break
        except Exception:
            pass

    total_cores = psutil.cpu_count()
    physical_cores = psutil.cpu_count(logical=False)

    cpu_usage = psutil.cpu_percent()
    cpu_freq = psutil.cpu_freq()
    cpu_freq_str = f"{cpu_freq.current:.0f} MHz" if cpu_freq else "N/A"

    cpu_model = "N/A"
    try:
        if platform.system() == "Linux":
            cpu_model = subprocess.check_output("cat /proc/cpuinfo | grep 'model name' | head -n 1 | cut -d: -f2", shell=True).decode().strip()
        elif platform.system() == "Darwin":
            cpu_model = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"]).decode().strip()
    except Exception:
        pass

    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage('/')

    # Package Stats
    python_version = platform.python_version()
    pyrogram_version = pyrogram.__version__
    motor_version = motor.version
    pymongo_version = pymongo.version

    bot_uptime_str = get_readable_time(int(bot_uptime))
    os_uptime_str = get_readable_time(int(time.time() - psutil.boot_time()))

    stats = f"""<b>📦 REPOSITORY STATISTICS</b>
<b>Branch:</b> {branch}
<b>Commit Date:</b> {commit_date_str}
<b>Commit Age:</b> {commit_age}
<b>Last Commit:</b> {last_commit}

<b>💻 OS STATISTICS</b>
<b>OS:</b> {os_dist}, {platform.release()}
<b>Total Cores:</b> {total_cores}
<b>Physical Cores:</b> {physical_cores}

<b>CPU:</b> [{get_progress_bar(cpu_usage)}] {cpu_usage}% | {cpu_freq_str}
<b>CPU Model:</b> {cpu_model}
<b>RAM:</b> [{get_progress_bar(ram.percent)}] {ram.percent}%
<b>DISK:</b> [{get_progress_bar(disk.percent)}] {disk.percent}%
<b>SWAP:</b> [{get_progress_bar(swap.percent)}] {swap.percent}%

<b>Disk Free:</b> {humanbytes(disk.free)}
<b>Disk Used:</b> {humanbytes(disk.used)}
<b>Disk Space:</b> {humanbytes(disk.total)}

<b>Memory Free:</b> {humanbytes(ram.available)}
<b>Memory Used:</b> {humanbytes(ram.used)}
<b>Memory Swap:</b> {humanbytes(swap.used)}
<b>Memory Total:</b> {humanbytes(ram.total)}

<b>📚 PACKAGES STATISTICS</b>
<b>Python:</b> {python_version}
<b>Pyrogram:</b> {pyrogram_version}
<b>Motor:</b> {motor_version}
<b>Pymongo:</b> {pymongo_version}

<b>Bot Uptime:</b> {bot_uptime_str}
<b>OS Uptime:</b> {os_uptime_str}"""
    return stats
