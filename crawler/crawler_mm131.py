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
base_url="https://mm131.pro"

class Spider():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 Safari/537.36",
        "Referer": base_url
    }

    def __init__(self, page_num, img_path, thread_num, type_id=1, type="home",tagslist=["性感美女","诱惑美女","大胸美女","萌妹子"]):
        self.page_num = page_num
        self.img_path = img_path
        self.thread_num = thread_num
        self.type_id = type_id
        self.type = type
        self.tagslist= tagslist
        self.rlock = threading.RLock()
        self.page_url_list = []
        self.img_url_list = []
        self.session = build_session(headers=self.headers)

    def get_url(self):
        for i in range(1,self.page_num+1):
            page = fetch(self.session, base_url+"/e/action/ListInfo/?classid="+str(self.type_id), headers=self.headers)
            if page is None:
                continue
            soup = BeautifulSoup(page.text, "html.parser")
            try:
                page_div = soup.find("dl", class_="list-left public-box").find_all("dd")
            except:
                print("采集错误，跳过本条")
                continue
            del page_div[-1]
            for dd in page_div:
                url = dd.find("a").get("href")
                self.page_url_list.append(base_url+url)

    def get_img(self,url):
        db = create_db_connection(dbhost)
        cursor = db.cursor()
        tagidlist = []
        try:
            page = fetch(self.session, url, headers=self.headers)
            if page is None:
                return
            page.encoding='UTF-8'
            soup = BeautifulSoup(page.text, "html.parser")
            if not soup.title or not soup.title.string:
                print("详情页结构异常：" + url)
                return
            title = soup.title.string.replace("_znns.com宅男钕神",'')
            title = title.replace("_znns.com",'')
            isExists = cursor.execute("SELECT title FROM images_page WHERE title =" + "'" + title + "'" + " limit 1;")
            if isExists != 0:
                print("isExists:" + title)
            else:
                tagslist = re.findall('<meta name="keywords" content="(.*?)" />', page.text)
                for tags in tagslist:
                    for tag in tags.split(","):
                        sqltag = "SELECT * FROM images_tag WHERE tag =" + "'" + tag + "'" + " limit 1;"
                        isExiststag = cursor.execute(sqltag)
                        if isExiststag == 0:
                            cursor.execute("INSERT INTO images_tag (tag) VALUES (%s)", tag)
                        cursor.execute("SELECT id FROM images_tag WHERE tag =" + "'" + tag + "'")
                        for id in cursor.fetchall():
                            tagidlist.append(id[0])
                p = (
                title, str(tagidlist), time.strftime('%Y-%m-%d', time.localtime(time.time())), self.type_id, "1", url)
                cursor.execute(
                    "INSERT INTO images_page (title,tagid,sendtime,typeid,firstimg,crawler) VALUES (%s,%s,%s,%s,%s,%s)", p)
                print("down：" + title)
                pageid = cursor.lastrowid
                img_num_soup = soup.find("div", class_="content-page").find("span").text
                img_num = "".join(re.findall(r"\d", img_num_soup))
                for i in range(1, int(img_num)):
                    headers = self.headers.copy()
                    headers.update({"Referer":url})
                    id = url.split("/")[-1].split(".")[0]
                    if i==1:
                        img_page_url=url
                    else:
                        img_page_url = "/".join(url.split("/")[0:-1]) + "/" + id + "_" + str(i) + ".html"
                    img_page = fetch(self.session, img_page_url, headers=headers, referer=url)
                    if img_page is None:
                        continue
                    img_soup=BeautifulSoup(img_page.text,"html.parser")
                    image_root = img_soup.find("div",class_="content-pic")
                    if not image_root or not image_root.find("img"):
                        continue
                    img_url = image_root.find("img").get("src")
                    img_name =img_url.split("/")[-1]
                    id=url.split("/")[-1].split(".")[0]
                    img_loc_path = self.img_path + time.strftime('%Y%m%d', time.localtime(
                        time.time())) + "/" + id + "/" +img_name
                    if i == 1:
                        cursor.execute(
                            "UPDATE images_page SET firstimg = " + "'" + img_loc_path + "'" + " WHERE id=" + "'" + str(
                                pageid) + "'")
                    imgp = pageid, img_loc_path,img_url
                    cursor.execute("INSERT INTO images_image (pageid,imageurl,originurl) VALUES (%s,%s,%s)", imgp)
                    i += 1
                    data={"img_url":img_url,"Referer":url,"id":id}
                    if data in self.img_url_list:
                        continue
                    else:
                        self.img_url_list.append(data)
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
            download_file(self.session, imgsrc, dest_path, headers=headers, referer=Referer)

    def run_page(self):
        while True:
            self.rlock.acquire()
            if len(self.page_url_list) == 0:
                self.rlock.release()
                break
            else:
                try:
                    page_url = self.page_url_list.pop()
                except Exception as e:
                    print(e)
                    pass
                self.rlock.release()
                try:
                    self.get_img(page_url)
                except Exception as e:
                    print(e)
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
                    print(e)
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


# page是采集深度，从1开始，采集第一页即采集最新发布。type是源站分类，type_id是对应本站分类的id
if __name__ == "__main__":
    for i in [{"page": 1, "type": "xinggan", "type_id": 1},{"page":1,"type":"qingchun","type_id": 2}]:
        spider = Spider(page_num=i.get("page"), img_path='/static/images/', thread_num=2, type_id=i.get("type_id"),
                        type=i.get("type"),tagslist=["性感美女","诱惑美女","大胸美女","萌妹子"])
        spider.get_url()
        if not spider.page_url_list:
            print("未获取到可用列表，跳过 {}".format(i.get("type")))
            continue
        spider.run_1()
        if not spider.img_url_list:
            print("未获取到可下载图片，跳过 {}".format(i.get("type")))
            continue
        spider.run_2()
