#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import shutil
import threading
import time
from flask import Flask, render_template_string, request, url_for
import signal

app = Flask(__name__)

# 媒体库根目录，请根据实际情况修改
MEDIA_DIR = "/data/gdemby/animation/动漫"
# 删除时实际移动的目标根目录（更新后的路径）
DELETED_DIR = "/data/.deleted/gdemby/animation/动漫/"

def scan_files():
    """
    遍历 MEDIA_DIR 目录，查找所有 .mkv 和 .mp4 文件，
    并提取文件对应的剧名（取文件所在目录的上上级目录名称）、
    集数（SxxExx），以及对应的季号和集号用于排序。
    返回一个列表，每个元素为字典：
      {
         'path': 文件完整路径,
         'rel_path': 相对于 MEDIA_DIR 的相对路径,
         'show': 剧名,
         'episode': 集数字符串,
         'season_num': 季号 (整数),
         'ep_num': 集号 (整数),
         'duplicate': 是否重复（同一剧+集出现多次）
      }
    """
    files_data = []
    for root, dirs, files in os.walk(MEDIA_DIR):
        for file in files:
            if file.lower().endswith('.mkv') or file.lower().endswith('.mp4'):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, MEDIA_DIR)
                parts = rel_path.split(os.sep)
                # 剧名取所在目录的上上级目录名称，要求目录结构至少为：<剧名>/<其它目录>/<文件>
                show = parts[0] if len(parts) >= 3 else ""
                # 匹配 SxxExx（不区分大小写）
                m = re.search(r'[Ss](\d{2})[Ee](\d{2})', full_path)
                if m:
                    episode = m.group(0)
                    season_num = int(m.group(1))
                    ep_num = int(m.group(2))
                else:
                    episode = ""
                    season_num = 0
                    ep_num = 0
                files_data.append({
                    'path': full_path,
                    'rel_path': rel_path,
                    'show': show,
                    'episode': episode,
                    'season_num': season_num,
                    'ep_num': ep_num,
                })

    # 统计每个剧集出现的次数（key 为 (剧名, 集数)）
    count_map = {}
    for item in files_data:
        key = (item['show'], item['episode'])
        count_map[key] = count_map.get(key, 0) + 1
    for item in files_data:
        key = (item['show'], item['episode'])
        item['duplicate'] = count_map.get(key, 0) > 1

    files_data.sort(key=lambda x: (x['show'], x['season_num'], x['ep_num'], x['path']))
    return files_data

def scan_deleted_files():
    """
    遍历 DELETED_DIR 目录，查找所有 .mkv 和 .mp4 文件，
    并提取文件对应的剧名（取文件所在目录的上上级目录名称）、
    集数（SxxExx），以及对应的季号和集号用于排序。
    返回一个列表，每个元素为字典，结构同 scan_files()。
    """
    files_data = []
    for root, dirs, files in os.walk(DELETED_DIR):
        for file in files:
            if file.lower().endswith('.mkv') or file.lower().endswith('.mp4'):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, DELETED_DIR)
                parts = rel_path.split(os.sep)
                show = parts[0] if len(parts) >= 3 else ""
                m = re.search(r'[Ss](\d{2})[Ee](\d{2})', full_path)
                if m:
                    episode = m.group(0)
                    season_num = int(m.group(1))
                    ep_num = int(m.group(2))
                else:
                    episode = ""
                    season_num = 0
                    ep_num = 0
                files_data.append({
                    'path': full_path,
                    'rel_path': rel_path,
                    'show': show,
                    'episode': episode,
                    'season_num': season_num,
                    'ep_num': ep_num,
                })

    count_map = {}
    for item in files_data:
        key = (item['show'], item['episode'])
        count_map[key] = count_map.get(key, 0) + 1
    for item in files_data:
        key = (item['show'], item['episode'])
        item['duplicate'] = count_map.get(key, 0) > 1

    files_data.sort(key=lambda x: (x['show'], x['season_num'], x['ep_num'], x['path']))
    return files_data

def remove_empty_dirs(path, root):
    """
    递归删除 path 下的所有空目录，若某个子目录为空则删除，
    但不删除 root 目录本身。
    """
    # 遍历当前目录下的所有项
    for entry in os.listdir(path):
        full_path = os.path.join(path, entry)
        if os.path.isdir(full_path):
            remove_empty_dirs(full_path, root)
    # 删除当前目录（如果不是根目录且为空）
    if path != root and not os.listdir(path):
        try:
            os.rmdir(path)
            print(f"删除空目录: {path}")
        except Exception as e:
            print(f"删除空目录 {path} 失败：{e}")

# HTML 模板，重复剧集显示红色，并在后面添加“重复”字样
template = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>番剧清理工具</title>
    <style>
        .duplicate { color: red; }
        table { border-collapse: collapse; }
        td, th { padding: 8px; border: 1px solid #ccc; }
    </style>
</head>
<body>
    <h1>番剧文件列表</h1>
    <form method="post" action="{{ url_for('delete') }}">
      <table>
        <tr>
          <th>选择</th>
          <th>文件路径</th>
          <th>剧集</th>
        </tr>
        {% for file in files %}
        <tr>
          <td><input type="checkbox" name="selected" value="{{ file.path }}"></td>
          <td>{{ file.path }}</td>
          <td {% if file.duplicate %}class="duplicate"{% endif %}>
              {{ file.show }} {{ file.episode }}{% if file.duplicate %} 重复{% endif %}
          </td>
        </tr>
        {% endfor %}
      </table>
      <br>
      <input type="submit" value="删除选中的文件">
    </form>
    <br>
    <form method="get" action="{{ url_for('deleted') }}">
      <input type="submit" value="显示已删除的文件">
    </form>
    <br>
    <form method="post" action="{{ url_for('shutdown') }}">
      <input type="submit" value="关闭服务">
    </form>
</body>
</html>
"""

deleted_template = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>已删除的番剧文件</title>
    <style>
        .duplicate { color: red; }
        table { border-collapse: collapse; }
        td, th { padding: 8px; border: 1px solid #ccc; }
    </style>
</head>
<body>
    <h1>已删除的番剧文件列表</h1>
    <form method="post" action="{{ url_for('restore') }}">
      <table>
        <tr>
          <th>选择</th>
          <th>文件路径</th>
          <th>剧集</th>
        </tr>
        {% for file in files %}
        <tr>
          <td><input type="checkbox" name="selected" value="{{ file.path }}"></td>
          <td>{{ file.path }}</td>
          <td {% if file.duplicate %}class="duplicate"{% endif %}>
              {{ file.show }} {{ file.episode }}{% if file.duplicate %} 重复{% endif %}
          </td>
        </tr>
        {% endfor %}
      </table>
      <br>
      <input type="submit" value="恢复选中的文件">
    </form>
    <br>
    <a href="{{ url_for('index') }}">返回主列表</a>
</body>
</html>
"""

@app.route("/")
def index():
    files = scan_files()
    return render_template_string(template, files=files)

@app.route("/delete", methods=["POST"])
def delete():
    """
    处理删除请求，将选中的文件移动到 DELETED_DIR 下，
    同时保持原来的相对目录结构。
    """
    selected_files = request.form.getlist("selected")
    messages = []
    for file_path in selected_files:
        if not os.path.exists(file_path):
            messages.append(f"文件不存在: {file_path}")
            continue
        try:
            # 计算相对于 MEDIA_DIR 的路径，并拼接到 DELETED_DIR 下
            rel_path = os.path.relpath(file_path, MEDIA_DIR)
            dest_path = os.path.join(DELETED_DIR, rel_path)
            dest_dir = os.path.dirname(dest_path)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(file_path, dest_path)
            messages.append(f"移动成功: <br>{file_path} <br>→ {dest_path}")
        except Exception as e:
            messages.append(f"移动失败: {file_path} ，错误: {str(e)}")
    result_html = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>删除结果</title>
    </head>
    <body>
      <h2>操作结果</h2>
      <p>{}</p>
      <p><a href="{}">返回列表</a></p>
    </body>
    </html>
    """.format("<br><br>".join(messages), url_for('index'))
    return result_html

@app.route("/deleted")
def deleted():
    files = scan_deleted_files()
    return render_template_string(deleted_template, files=files)

@app.route("/restore", methods=["POST"])
def restore():
    """
    处理恢复请求，将选中的文件从 DELETED_DIR 移动回 MEDIA_DIR，
    同时保持原来的相对目录结构。
    恢复完成后，递归删除 DELETED_DIR 内空目录。
    """
    selected_files = request.form.getlist("selected")
    messages = []
    for file_path in selected_files:
        if not os.path.exists(file_path):
            messages.append(f"文件不存在: {file_path}")
            continue
        try:
            rel_path = os.path.relpath(file_path, DELETED_DIR)
            dest_path = os.path.join(MEDIA_DIR, rel_path)
            dest_dir = os.path.dirname(dest_path)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(file_path, dest_path)
            messages.append(f"恢复成功: <br>{file_path} <br>→ {dest_path}")
        except Exception as e:
            messages.append(f"恢复失败: {file_path} ，错误: {str(e)}")
    # 递归删除 DELETED_DIR 下所有空目录（包括可能已空的上层目录）
    remove_empty_dirs(DELETED_DIR, DELETED_DIR)
    result_html = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>恢复结果</title>
    </head>
    <body>
      <h2>操作结果</h2>
      <p>{}</p>
      <p><a href="{}">返回已删除列表</a></p>
    </body>
    </html>
    """.format("<br><br>".join(messages), url_for('deleted'))
    return result_html

#def shutdown_server():
#    """
#    关闭服务器。若在 request.environ 中找不到 Werkzeug 的 shutdown 函数，
#    则延迟 1 秒后强制退出进程，确保响应能返回给客户端。
#    """
#    func = request.environ.get("werkzeug.server.shutdown")
#    if func is None:
#        # 延迟 1 秒后退出，确保本次请求的响应能先返回
#        threading.Timer(1.0, lambda: os._exit(0)).start()
#    else:
#        func()

def shutdown_server():
    """关闭服务器并终止进程"""
    os.kill(os.getpid(), signal.SIGINT)

@app.route("/shutdown", methods=["POST"])
def shutdown():
    shutdown_server()
    return "<h2>服务器正在关闭…</h2>"

if __name__ == "__main__":
    # 绑定到 IPv6 上（host 设置为 "::"）
    app.run(host="::", port=5000)

