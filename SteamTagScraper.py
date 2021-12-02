from selenium import webdriver
from bs4 import BeautifulSoup
from selenium.webdriver.support.ui import WebDriverWait
from time import sleep
from dotenv import load_dotenv
import requests, pymongo, os, datetime

"""
Web Scraper
Scrapes Steam store page with games tagged as "souls-like" and adds them to the database
Plans to call this program from the windows scheduler
"""

load_dotenv()
client = os.getenv('client')
DB_CLIENT = pymongo.MongoClient(client)
DB = DB_CLIENT['steamData']
APPDATA = DB['appData']

MAIN = 'https://store.steampowered.com/search/?sort_by=Released_DESC&tags=29482&ignore_preferences=1'


def load_main_page():
    """ 
    Loads + scrapes entire infinite-scroll page
    """

    # Load full page:
    driver = webdriver.Chrome(executable_path="c:\webdrivers\chromedriver.exe")
    driver.get(MAIN)

    #This code will scroll down to the end
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        # Action scroll down
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        sleep(0.23)

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    
    return driver.page_source


def scrape_main_page(html=None):
    # Scrape page for each application in list, then call method to scrape individual store page    
    if html:
        soup = BeautifulSoup(html, features='html.parser')
    else:   # Used for testing without selenium
        reqst = requests.get(MAIN)
        soup = BeautifulSoup(reqst.content, features='html.parser')

    container = soup.find('div', {'id' : 'search_resultsRows'})
    apps_data = container.find_all('a', {'data-gpnav' : 'item'})
    # applications = soup.find_all('a', {'class' : 'search_result_row ds_collapse_flag  app_impression_tracked'})
    print(len(apps_data))

    for tag in apps_data:
        app_id = tag['data-ds-appid']
        store_page = tag.get('href')
        title = tag.find('span', {'class' : 'title'}).text.replace('&amp;', '&').strip()
        try:
            release_date = tag.find('div', {'class': 'col search_released responsive_secondrow'}).text
        except:
            print('no release date')
            release_date = None
        thumbnail = f'https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg'

        if title[-5:].lower() == ' demo':
            title = title[:-5]
            demo = True
        else:
            demo = False

        if APPDATA.find_one({'demo': True, 'title': title}) is not None:
            APPDATA.delete_one({'demo': True, 'title': title})
        
        try:
            APPDATA.insert_one({ '_id': app_id, 
                    'title': title, 
                    'releaseDate': release_date, 
                    'demo': demo,
                    'storePage': store_page, 
                    'thumbnail': thumbnail,
                    'souls': 0,
                    'notSouls': 0
                })
        except pymongo.errors.DuplicateKeyError:
            old = APPDATA.find_one({'_id': app_id})
            print(f'Duplicate key error for ID {app_id}, ({title})\nOld title =', old['title'])
        
        
        # print(f'ID: {app_id}\nTitle: {title},\t link: {store_page}\nrelease: {release_date}, Demo = {demo}')
        

def build_descriptions():
    cursor = APPDATA.find()
    for doc in cursor:
        r = requests.get(doc['storePage'])
        soup = BeautifulSoup(r.content, features='html.parser')
        try:
            desc = soup.find('div', {'class': 'game_description_snippet'}).text.strip()
        except AttributeError:
            APPDATA.update_one({'_id': doc['_id']}, {'$set': {'desc': None}})
            continue

        if doc['storePage'][-20:-15] == '?snr=':
            print('newURL = ', doc['storePage'][:-20])
            APPDATA.update_one({'_id': doc['_id']}, {'$set': {'desc': desc, 'storePage': doc['storePage'][:-20]}})
        else:
            APPDATA.update_one({'_id': doc['_id']}, {'$set': {'desc': desc}})


def main():
    # source = load_main_page()
    # scrape_main_page(source)
    # build_descriptions()

    # cursor = APPDATA.find({'storePage': {'$regex': 'snr'}})
    # for doc in cursor:
        # idx = doc['storePage'].index('?')
        # APPDATA.update_one({'_id': doc['_id']}, {'$set': {'storePage': doc['storePage'][:idx]}})
       

    APPDATA.update_many({'notSouls': {'$ne': 0}, 'souls': {'$ne': 0}}, {'$set': {"notSouls": 0, 'souls': 0}})
    APPDATA.update_many({'noSouls': {'$exists': True}}, {'$unset': {'noSouls': ""}})



if __name__ == "__main__":
    main()