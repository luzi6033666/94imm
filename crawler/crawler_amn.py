# coding='UTF-8'
import sys
sys.path.append('../')
from bs4 import BeautifulSoup
import threading,time,os,re
from config import mysql_config
from common import build_session, create_db_connection, download_file, fetch
# 数据库连接信息
dbhost = {
    "host": mysql_config['HOST'],
    "dbname": mysql_config['NAME'],
    "user": mysql_config['USER'],
    "password": mysql_config['PASSWORD']
}

base_url="https://www.2meinv.com/"
tag_url="https://www.2meinv.com/tags-{}-{}.html"
index_url="https://www.2meinv.com/index-1.html"
img_path='/static/images/'

class Spider():
    def __init__(self, start_page_num, end_page_num,img_path, thread_num, type="home",type_id=0):
        self.start_page_num = start_page_num
        self.end_page_num=end_page_num
        self.img_path = img_path
        self.thread_num = thread_num
        self.type = type
        self.type_id=type_id
        self.page_url_list = []
        self.img_url_list = []
        self.rlock = threading.RLock()
        self.session = build_session()

    def get_url(self):
        for i in range(self.start_page_num, self.end_page_num):
            target_url = index_url.format(str(i)) if self.type_id == 0 else tag_url.format(self.type, str(i))
            response = fetch(self.session, target_url)
            if response is None:
                continue
            page = response.text
            soup = BeautifulSoup(page, "html.parser")
            detail_list = soup.find("ul", class_="detail-list")
            if not detail_list:
                print("未找到列表页结构：" + target_url)
                continue
            page_base_url = detail_list.find_all("li")
            for page_url in page_base_url:
                url = page_url.find("a",class_="dl-pic").get("href")
                self.page_url_list.append(url)

    def get_img(self,url):
        tagidlist=[]
        db = create_db_connection(dbhost)
        cursor = db.cursor()
        try:
            page = fetch(self.session, url)
            if page is None:
                return
            soup = BeautifulSoup(page.text, "html.parser")
            if not soup.title or not soup.title.string:
                print("详情页结构异常：" + url)
                return
            title=soup.title.string.replace("_爱美女","")
            if self.type_id == 0:
                if "袜" in title or "丝" in title or "腿" in title:
                    self.type_id = 2
                elif "青春" in title or "清纯" in title:
                    self.type_id = 3
                elif "萝莉" in title:
                    self.type_id = 4
                else:
                    self.type_id = 1
            isExists = cursor.execute("SELECT title FROM images_page WHERE title =" + "'" + title + "'" + " limit 1;")
            if isExists != 0:
                print("已采集：" , title)
            else:
                print("正在采集：", title)
                tags=soup.find(attrs={"name":"Keywords"})['content'].split(",")
                for tag in tags:
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
                img_soup=soup.find("div",class_="page-show").text
                img_nums=re.sub(r"\D", "", img_soup)
                if len(img_nums)==6:
                    img_num=img_nums[-2:]
                elif len(img_nums)<6:
                    img_num = img_nums[-1]
                elif len(img_nums)>6:
                    img_num = img_nums[-3:]
                id=url.split("-")[-1].split(".")[0]
                for i in range(1,int(img_num)+1):
                    img_page_url=base_url+"article-"+id+"-"+str(i)+".html"
                    img_page = fetch(self.session, img_page_url, referer=url)
                    if img_page is None:
                        continue
                    img_soup=BeautifulSoup(img_page.text, "html.parser")
                    image_root = img_soup.find("div",class_="pp hh")
                    if not image_root or not image_root.find("img"):
                        continue
                    img_url=image_root.find("img").get("src")
                    img_name = img_url.split("/")[-1]
                    img_loc_path = self.img_path + time.strftime('%Y%m%d', time.localtime(
                        time.time())) + "/" + id + "/" + img_name
                    imgp = pageid, img_loc_path,img_url
                    cursor.execute("INSERT INTO images_image (pageid,imageurl,originurl) VALUES (%s,%s,%s)", imgp)
                    if i==1:
                        cursor.execute(
                            "UPDATE images_page SET firstimg = " + "'" + img_loc_path + "'" + " WHERE id=" + "'" + str(
                                pageid) + "'")
                    self.img_url_list.append({"img_url":img_url,"Referer":url,"id":id})
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
        path = img_path + time.strftime('%Y%m%d', time.localtime(time.time())) + "/"
        page_id = id
        isdata = os.path.exists("../" + path + page_id)
        if not isdata:
            os.makedirs("../" + path + page_id)
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
                page_url = self.page_url_list.pop()
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

# start_page是采集开始也，end是采集结束页，type不用修改，自动分类，起始页为1
if __name__ == "__main__":
    cl_list=[{"start_page": 1,"end_page":2, "type": "Cosplay", "type_id":6},
             {"start_page": 1,"end_page":2, "type": "性感", "type_id":1},
             {"start_page": 1, "end_page": 2, "type": "丝袜", "type_id": 3},
             {"start_page": 1, "end_page": 2, "type": "美腿", "type_id": 4},
             {"start_page": 1, "end_page": 2, "type": "美胸", "type_id": 5},
             {"start_page": 1, "end_page": 2, "type": "制服诱惑", "type_id": 7}
             ]


    for i in cl_list:
        spider = Spider(start_page_num=i.get("start_page"),end_page_num=i.get("end_page"), img_path='/static/images/', thread_num=3,
                        type=i.get("type"),type_id=i.get("type_id"))
        spider.get_url()
        if not spider.page_url_list:
            print("未获取到可用列表，跳过 {}".format(i.get("type")))
            continue
        spider.run_1()
        if not spider.img_url_list:
            print("未获取到可下载图片，跳过 {}".format(i.get("type")))
            continue
        spider.run_2()
