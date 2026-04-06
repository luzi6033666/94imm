# coding='UTF-8'
import sys

sys.path.append('../')
from bs4 import BeautifulSoup
import threading, time, os
from config import mysql_config
from common import build_session, create_db_connection, download_file, fetch


class Spider():
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/65.0.3325.181 Safari/537.36',
        'Referer': "https://www.mzitu.com"
    }
    dbhost = {
        "host": mysql_config['HOST'],
        "dbname": mysql_config['NAME'],
        "user": mysql_config['USER'],
        "password": mysql_config['PASSWORD']
    }

    def __init__(self, page_num=10, img_path='imgdir', thread_num=5, type="xinggan", type_id=1):
        self.spider_url = 'https://www.mzitu.com/'
        self.page_number = int(page_num)
        self.img_path = img_path
        self.thread_num = thread_num
        self.type = type
        self.type_id = type_id
        self.page_url_list = []
        self.img_url_list = []
        self.rlock = threading.RLock()
        self.session = build_session(headers=self.headers)

    def get_url(self):
        for i in range(1, self.page_number + 1):
            page_url = self.spider_url + "/" + self.type if i == 1 else self.spider_url + "/" + self.type + "/page/" + str(i)
            response = fetch(self.session, page_url)
            if response is None:
                continue
            page = response.text
            soup = BeautifulSoup(page, "html.parser")
            post_list = soup.find("div", class_="postlist")
            if not post_list:
                print("未找到列表页结构：" + page_url)
                continue
            page_base_url = post_list.find_all("li")
            for page_url in page_base_url:
                url = page_url.find("a").get("href")
                self.page_url_list.append(url)

    def get_img_url(self):
        db = create_db_connection(self.dbhost)
        cursor = db.cursor()
        try:
            for img_base_url in self.page_url_list:
                tagidlist = []
                response = fetch(self.session, img_base_url)
                if response is None:
                    continue

                img_soup = BeautifulSoup(response.text, "html.parser")
                pagenavi = img_soup.find("div", class_="pagenavi")
                main_image = img_soup.find("div", class_="main-image")
                title_node = img_soup.find("h2", class_="main-title")
                tag_root = img_soup.find("div", class_="main-tags")
                if not pagenavi or not main_image or not title_node or not tag_root:
                    print("详情页结构异常：" + img_base_url)
                    continue

                main_image_src = main_image.find("img").get("src")
                img_num = pagenavi.text.split("…")[-1][0:-5]
                img_url = main_image_src.split("/")[0:-1]
                img_surl = "/".join(img_url)
                title = title_node.text
                is_exists = cursor.execute("SELECT 1 FROM images_page WHERE title = %s LIMIT 1", (title,))
                tag_list = tag_root.find_all("a")
                if is_exists == 1:
                    print("已采集：" + title)
                    continue

                for tags in tag_list:
                    tag = tags.text
                    print(tag)
                    is_exists_tag = cursor.execute("SELECT 1 FROM images_tag WHERE tag = %s LIMIT 1", (tag,))
                    if is_exists_tag != 1:
                        cursor.execute("INSERT INTO images_tag (tag) VALUES (%s)", (tag,))
                    cursor.execute("SELECT id FROM images_tag WHERE tag = %s", (tag,))
                    for tag_id in cursor.fetchall():
                        tagidlist.append(tag_id[0])

                p = (title, str(tagidlist), time.strftime('%Y-%m-%d', time.localtime(time.time())), self.type_id, "1")
                cursor.execute(
                    "INSERT INTO images_page (title,tagid,sendtime,typeid,firstimg) VALUES (%s,%s,%s,%s,%s)",
                    p,
                )
                print("开始采集：" + title)
                pageid = cursor.lastrowid
                for i in range(1, int(img_num)):
                    temp_url = main_image_src.split("/")
                    path = temp_url[-1][0:3]
                    new_url = img_surl + "/" + path + str("%02d" % i) + ".jpg"
                    img_src = temp_url[-3] + "/" + temp_url[-2] + "/" + path + str("%02d" % i) + ".jpg"
                    cursor.execute(
                        "INSERT INTO images_image (pageid,imageurl) VALUES (%s,%s)",
                        (pageid, self.img_path + img_src),
                    )
                    if i == 1:
                        cursor.execute(
                            "UPDATE images_page SET firstimg = %s WHERE id = %s",
                            (self.img_path + img_src, pageid),
                        )
                    self.img_url_list.append(new_url)
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            cursor.close()
            db.close()

    def down_img(self, imgsrc):
        path = imgsrc.split("/")[-3] + "/" + imgsrc.split("/")[-2]
        if os.path.exists("../" + self.img_path + path) == False:
            os.makedirs("../" + self.img_path + path)
        isfile = os.path.exists("../" + self.img_path + path + "/" + imgsrc.split("/")[-1])
        if isfile == False:
            dest_path = "../" + self.img_path + path + "/" + imgsrc.split("/")[-1]
            print("下载图片：" + self.img_path + path + "/" + imgsrc.split("/")[-1])
            if not download_file(
                self.session,
                imgsrc,
                dest_path,
                headers=self.headers,
            ):
                return

    def down_url(self):
        while True:
            self.rlock.acquire()
            if len(self.img_url_list) == 0:
                self.rlock.release()
                break
            else:
                img_url = self.img_url_list.pop()
                self.rlock.release()
                try:
                    self.down_img(img_url)
                except Exception as e:
                    pass

    def run(self):
        download_threads = []
        for img_th in range(self.thread_num):
            download_t = threading.Thread(target=self.down_url)
            download_threads.append(download_t)
            download_t.start()

        for download_t in download_threads:
            download_t.join()


if __name__ == '__main__':
    for i in [{"page": 1, "type": "xinggan", "type_id": 1},]:
        spider = Spider(page_num=i.get("page"), img_path='/static/images/', thread_num=10, type_id=i.get("type_id"),
                        type=i.get("type"))
        spider.get_url()
        if not spider.page_url_list:
            print("未获取到可用列表，跳过 {}".format(i.get("type")))
            continue
        spider.get_img_url()
        if not spider.img_url_list:
            print("未获取到可下载图片，跳过 {}".format(i.get("type")))
            continue
        spider.run()
