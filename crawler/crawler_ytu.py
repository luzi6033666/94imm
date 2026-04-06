# coding='UTF-8'

import sys

sys.path.append('../')
from bs4 import BeautifulSoup
import threading, time, os, re
from config import mysql_config
from common import build_session, create_db_connection, download_file, fetch
# 数据库连接信息
dbhost = {
    "host": mysql_config['HOST'],
    "dbname": mysql_config['NAME'],
    "user": mysql_config['USER'],
    "password": mysql_config['PASSWORD']
}

base_url="https://www.yeitu.com/meinv/"
img_path='/static/images/'

class Spider():
    def __init__(self, start_page_num,end_page_num, img_path, thread_num, type="home",type_id='1'):
        self.start_page_num = start_page_num
        self.end_page_num = end_page_num
        self.img_path = img_path
        self.thread_num = thread_num
        self.type = type
        self.type_id=type_id
        self.page_url_list = []
        self.img_url_list = []
        self.rlock = threading.RLock()
        self.exit = threading.Event()
        self.session = build_session()

    def get_url(self):
        for i in range(self.start_page_num, self.end_page_num + 1):
            if i==1:
                page_url=base_url + self.type
            else:
                page_url=base_url + self.type+"/"+str(i)+".html"
            response = fetch(self.session, page_url, timeout=5)
            if response is None:
                continue
            page = response.text
            soup = BeautifulSoup(page, "html.parser")
            page_base_url = soup.find_all("li",class_="image-box")
            for page_url in page_base_url:
                url = page_url.find("a").get("href")
                self.page_url_list.append(url)

    def get_img(self, url):
        tagidlist = []
        db = create_db_connection(dbhost)
        cursor = db.cursor()
        try:
            page = fetch(self.session, url, timeout=5)
            if page is None:
                return
            page.encoding="utf-8"
            soup = BeautifulSoup(page.text, "html.parser")
            if not soup.title or not soup.title.string:
                print("详情页结构异常：" + url)
                return
            title = soup.title.string.replace(" - 美女 - 亿图全景图库", "").replace(" ","")
            isExists = cursor.execute("SELECT title FROM images_page WHERE title =" + "'" + title + "'" + " limit 1;")
            if isExists != 0:
                print("已采集：" , title)
            else:
                print("正在采集：", title)
                tags = soup.find("div",class_="related_tag box").find("p").find_all("a")
                for tag_a in tags:
                    tag=tag_a.text
                    sqltag = "SELECT * FROM images_tag WHERE tag =" + "'" + tag + "'" + " limit 1;"
                    isExiststag = cursor.execute(sqltag)
                    if isExiststag == 0:
                        cursor.execute("INSERT INTO images_tag (tag) VALUES (%s)", tag)
                    cursor.execute("SELECT id FROM images_tag WHERE tag =" + "'" + tag + "'")
                    for id in cursor.fetchall():
                        tagidlist.append(id[0])
                p = (title, str(tagidlist), time.strftime('%Y-%m-%d', time.localtime(time.time())), self.type_id, "1",url)
                cursor.execute("INSERT INTO images_page (title,tagid,sendtime,typeid,firstimg,crawler) VALUES (%s,%s,%s,%s,%s,%s)", p)
                pageid = cursor.lastrowid
                img_num=soup.find("div",id="pages").text.replace("上一页","").replace("下一页","").split("..")[-1].replace("  ","")
                for i in range(1, int(img_num) + 1):
                    img_p_url=".".join(url.split(".")[0:-1])+"_"+str(i)+".html"
                    img_p_page = fetch(self.session, img_p_url, referer=url, timeout=5)
                    if i != 1 and img_p_page is None:
                        continue
                    if i==1:
                        img_p = soup.find("div", class_="img_box").find("img").get("src")
                    else:
                        img_p_soup=BeautifulSoup(img_p_page.text,"html.parser")
                        img_p=img_p_soup.find("div",class_="img_box").find("img").get("src")
                    img_name = img_p.split("/")[-1]
                    img_base = img_name[8:12]
                    img_path = self.img_path + time.strftime('%Y%m%d', time.localtime(
                        time.time())) + "/" + img_base + "/"
                    imgp = pageid, img_path+img_name,img_p
                    cursor.execute("INSERT INTO images_image (pageid,imageurl,originurl) VALUES (%s,%s,%s)", imgp)
                    if i == 1:
                        cursor.execute(
                            "UPDATE images_page SET firstimg = " + "'" + img_path+img_name + "'" + " WHERE id=" + "'" + str(
                                pageid) + "'")
                    self.img_url_list.append({"img_url": img_p, "Referer": url,"id": img_base})
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
        isdata = os.path.exists("../" + path + page_id)
        if not isdata:
            os.makedirs("../" + path + page_id)
        isfile = os.path.exists("../" + path + page_id + "/" + imgsrc.split("/")[-1].split(".")[0] + ".jpg")
        if not isfile:
            dest_path = "../" + path + page_id + "/" + imgsrc.split("/")[-1].split(".")[0] + ".jpg"
            print("已保存：" + path + page_id + "/" + imgsrc.split("/")[-1].split(".")[0] + ".jpg")
            download_file(self.session, imgsrc, dest_path, headers=headers, referer=Referer, timeout=5)


    def run_page(self):
        while True:
            self.rlock.acquire()
            if len(self.page_url_list) == 0:
                self.rlock.release()
                break
            else:
                page_url = self.page_url_list.pop()
                self.rlock.release()
                try:
                    self.get_img(page_url)
                except Exception as e:
                    pass

    def run_img(self):
        while True:
            self.rlock.acquire()
            if len(self.img_url_list) == 0 :
                self.rlock.release()
                break
            else:
                urls = self.img_url_list.pop()
                url = urls.get("img_url")
                Referer = urls.get("Referer")
                id = urls.get("id")
                self.rlock.release()
                try:
                    self.down_img(url, Referer, id)
                except Exception as e:
                    pass

    def run_1(self):
        # 启动thread_num个进程来爬去具体的img url 链接
        url_threa_list=[]
        for th in range(self.thread_num):
            add_pic_t = threading.Thread(target=self.run_page)
            url_threa_list.append(add_pic_t)

        for t in url_threa_list:
            t.daemon = True
            t.start()

        for t in url_threa_list:
            t.join()

    def run_2(self):
        # 启动thread_num个来下载图片
        for img_th in range(self.thread_num):
            download_t = threading.Thread(target=self.run_img)
            download_t.start()


# type是源站分类，type_id是本站分类id，start_page是开始页，end_page是结束页
if __name__ == "__main__":
    for i in [{"start_page": 1,"end_page":1, "type": "xinggan","type_id":"1"},{"start_page": 1,"end_page":1, "type": "wangluomeinv","type_id":"8"},{"start_page": 1,"end_page":1, "type": "siwameitui","type_id":"3"}]:
        spider = Spider(start_page_num=i.get("start_page"),end_page_num=i.get("end_page"), img_path='/static/images/', thread_num=10,
                        type=i.get("type"))
        spider.get_url()
        if not spider.page_url_list:
            print("未获取到可用列表，跳过 {}".format(i.get("type")))
            continue
        spider.run_1()
        if not spider.img_url_list:
            print("未获取到可下载图片，跳过 {}".format(i.get("type")))
            continue
        spider.run_2()
