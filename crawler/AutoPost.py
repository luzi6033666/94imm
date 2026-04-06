# -*- coding: utf-8 -*-
import sys

sys.path.append('../')
import os
import random
import shutil
import time

import pymysql
from config import mysql_config

dbhost = {
    "host": mysql_config['HOST'],
    "dbname": mysql_config['NAME'],
    "user": mysql_config['USER'],
    "password": mysql_config['PASSWORD']
}

DEFAULT_TAGS = ['cosplay', '萝莉', '美腿', '丝袜', '少女']


def _base_name(path):
    return os.path.basename(os.path.normpath(path))


def _get_or_create_tag_ids(cursor, tags):
    tag_id_list = []
    for tag in tags:
        if cursor.execute("SELECT id FROM images_tag WHERE tag = %s LIMIT 1", (tag,)) == 1:
            tag_id_list.append(cursor.fetchone()[0])
            continue

        cursor.execute("INSERT INTO images_tag (tag) VALUES (%s)", (tag,))
        tag_id_list.append(cursor.lastrowid)
    return tag_id_list


def do_post(file_dir, sleep_time="0"):
    try:
        sleep_seconds = max(int(sleep_time), 0)
    except (TypeError, ValueError):
        sleep_seconds = 0

    db = pymysql.connect(
        host=dbhost.get("host"),
        user=dbhost.get("user"),
        password=dbhost.get("password"),
        database=dbhost.get("dbname"),
        charset="utf8mb4",
    )
    cursor = db.cursor()
    root_name = _base_name(file_dir)

    try:
        for current_root, _, file_names in os.walk(file_dir):
            title = _base_name(current_root)
            if title == root_name or not file_names:
                continue

            if cursor.execute("SELECT 1 FROM images_page WHERE title = %s LIMIT 1", (title,)) == 1:
                print("已存在：" + title)
            else:
                try:
                    tagidlist = _get_or_create_tag_ids(cursor, DEFAULT_TAGS)
                    page_info = (
                        title,
                        str(tagidlist),
                        time.strftime('%Y-%m-%d', time.localtime(time.time())),
                        "1",
                        "1",
                    )
                    cursor.execute(
                        "INSERT INTO images_page (title,tagid,sendtime,typeid,firstimg) VALUES (%s,%s,%s,%s,%s)",
                        page_info,
                    )
                    pageid = cursor.lastrowid
                    rpath = "".join(random.sample('abcdefghijklmnopqrstuvwxyz', 7))
                    target_dir = os.path.join("..", "static", "images", rpath)
                    if not os.path.exists(target_dir):
                        os.makedirs(target_dir)

                    for count, name in enumerate(sorted(file_names), start=1):
                        source_path = os.path.join(current_root, name)
                        rename = "{}.{}".format(count, name.split(".")[-1])
                        target_path = os.path.join(target_dir, rename)
                        shutil.move(source_path, target_path)
                        imgp = "/static/images/{}/{}".format(rpath, rename)
                        if count == 1:
                            cursor.execute("UPDATE images_page SET firstimg = %s WHERE id=%s", (imgp, pageid))
                        cursor.execute(
                            "INSERT INTO images_image (pageid,imageurl) VALUES (%s,%s)",
                            (pageid, imgp),
                        )
                    db.commit()
                except Exception as e:
                    db.rollback()
                    print(e)
                    continue

            try:
                os.removedirs(current_root)
            except OSError:
                print("目录不为空，无法删除")

            print("发布完成：" + title)
            if sleep_seconds:
                time.sleep(sleep_seconds)
    finally:
        cursor.close()
        db.close()

# do_post("输入图片所在目录","发布间隔时间，默认0，单位秒")
if __name__ == "__main__":
    print("图片所在目录：")
    path=input("")
    print("自动发布间隔，0为全部发布，单位秒")
    send_time=input("")
    do_post(path,send_time)
