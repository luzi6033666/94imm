# encoding: utf-8
import sys

sys.path.append('../')
from bs4 import BeautifulSoup
import threading, time, os
from config import mysql_config
from common import build_session, create_db_connection, download_file, fetch
# 数据库连接信息
dbhost = {
    "host": mysql_config['HOST'],
    "dbname": mysql_config['NAME'],
    "user": mysql_config['USER'],
    "password": mysql_config['PASSWORD']
}


class Spider():
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/65.0.3325.181 Safari/537.36',
        'Referer': "http://www.xgmmtk.com/"
    }
    def __init__(self, img_path='imgdir', thread_number=5):
        self.spider_url = 'http://www.xgmmtk.com/'
        self.img_path = img_path
        self.thread_num = thread_number
        self.page_url_list = []
        self.img_url_list = []
        self.rlock = threading.RLock()
        self.session = build_session(headers=self.headers)

    def get_url(self):
        page = fetch(self.session, "http://www.xgmmtk.com/")
        if page is None:
            return
        soup = BeautifulSoup(page.text, "html.parser")
        a_soup = soup.find_all("a")
        i = 1
        for a in a_soup:
            href = a.get("href")
            if not href:
                continue
            url = "http://www.xgmmtk.com/" + href.lstrip("/")
            self.page_url_list.append(url)
            i += 1
            if i > 20:
                break

    def get_img(self):
        db = create_db_connection(dbhost)
        cursor = db.cursor()
        try:
            while True:
                self.rlock.acquire()
                if len(self.page_url_list) == 0:
                    self.rlock.release()
                    break
                page_url = self.page_url_list.pop()
                self.rlock.release()

                page = fetch(self.session, page_url)
                if page is None:
                    continue

                soup = BeautifulSoup(page.text, "html.parser")
                if not soup.title or not soup.title.string:
                    print("详情页结构异常：" + page_url)
                    continue

                title = soup.title.string.replace("�", "")
                is_exists = cursor.execute("SELECT id FROM images_page WHERE title = %s LIMIT 1", (title,))
                if is_exists != 0:
                    print("已采集:" + page_url)
                    continue

                print("添加采集：", title)
                if "袜" in title or "丝" in title:
                    type_id = 3
                    tagidlist = [3679, 3700, 3719, 3628]
                elif "腿" in title:
                    type_id = 4
                    tagidlist = [3679, 3700, 3719, 3628]
                elif "青春" in title or "清纯" in title or "萝莉" in title:
                    tagidlist = [3694, 3627, 3635]
                    type_id = 2
                elif "胸" in title:
                    type_id = 5
                    tagidlist = [3694, 3627, 3635]
                else:
                    tagidlist = [3630, 3623, 3618, 3642]
                    type_id = 1

                page_id = page_url[page_url.find("?id=") + 4:].rstrip("/")
                if not page_id:
                    print("无法解析页面ID：" + page_url)
                    continue

                cursor.execute(
                    "INSERT INTO images_page (title,tagid,sendtime,typeid,firstimg,crawler) VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        title,
                        str(tagidlist),
                        time.strftime('%Y-%m-%d', time.localtime(time.time())),
                        type_id,
                        "1",
                        page_url,
                    ),
                )
                pageid = cursor.lastrowid
                img_list = soup.find_all("img")
                img_path = self.img_path + time.strftime('%Y%m%d', time.localtime(time.time())) + "/" + page_id + "/"
                for index, imgurl in enumerate(img_list):
                    img_src = imgurl.get("src")
                    if not img_src:
                        continue
                    imgsrc = "http://www.xgmmtk.com" + img_src
                    self.img_url_list.append({"img_url": imgsrc, "Referer": page_url, "id": page_id})
                    img_loc_path = img_path + imgsrc.split("/")[-1]
                    if index == 0:
                        cursor.execute("UPDATE images_page SET firstimg = %s WHERE id = %s", (img_loc_path, pageid))
                    else:
                        cursor.execute(
                            "INSERT INTO images_image (pageid,imageurl,originurl) VALUES (%s,%s,%s)",
                            (pageid, img_loc_path, imgsrc),
                        )
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            cursor.close()
            db.close()

    def down_img(self,imgsrc,Referer,id):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.81 Safari/537.36",
            "Referer": Referer
        }
        path = self.img_path + time.strftime('%Y%m%d', time.localtime(time.time())) + "/"
        page_id = id
        if not os.path.exists("../" + path + page_id):
            os.makedirs("../" + path + page_id)
        isfile = os.path.isfile("../" + path + page_id + "/" + imgsrc.split("/")[-1])
        if not isfile:
            dest_path = "../" + path + page_id + "/" + imgsrc.split("/")[-1]
            print("已保存：" ,imgsrc)
            if not download_file(
                self.session,
                imgsrc,
                dest_path,
                headers=headers,
            ):
                return



    def run_img(self):
        tries = 0
        while True:
            self.rlock.acquire()
            if len(self.img_url_list) == 0 :
                self.rlock.release()
                time.sleep(5)
                tries += 1
                if tries > 3:
                    break
                else:
                    continue
            else:
                tries = 0
                urls = self.img_url_list.pop()
                url = urls.get("img_url")
                Referer = urls.get("Referer")
                id = urls.get("id")
                self.rlock.release()
                try:
                    self.down_img(url, Referer, id)
                except Exception as e:
                    pass

    def run(self):
        download_threads = []
        for img_th in range(self.thread_num):
            download_t = threading.Thread(target=self.run_img)
            download_threads.append(download_t)
            download_t.start()

        worker_threads = []
        for img_th in range(self.thread_num):
            run_t = threading.Thread(target=self.get_img)
            worker_threads.append(run_t)
            run_t.start()

        for run_t in worker_threads:
            run_t.join()
        for download_t in download_threads:
            download_t.join()

if __name__ == "__main__":
    spider=Spider(img_path='/static/images/',thread_number=1)
    spider.get_url()
    if not spider.page_url_list:
        print("未获取到可用列表，跳过 xgmmtk")
        raise SystemExit(0)
    spider.run()
