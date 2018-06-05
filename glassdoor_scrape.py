# web scraping
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait as wait
from selenium.webdriver.chrome.options import Options
chrome_options = Options()
chrome_options.set_headless(headless=True) # decides whether to show the chrome window while executing web search

# parsing web pages
from bs4 import BeautifulSoup

# allow for scraping many pages at once
import threading

# assortment of other libraries
import re
import time
import string
import pandas as pd
import numpy as np
import arrow
import sys


class glassdoor_scraper():
    
    def __init__(self, job_search_terms, location_search_terms, all_pages=True, num_pages):
        
        # main parameters of the web scrape
        self.job_search_terms = job_search_terms
        self.location_search_terms = location_search_terms
        
        assert(len(job_search_terms) == len(location_search_terms)) # has to be equal
        
        # for storing data
        self.all_job_pages = [] # contains all scraped HTML pages
        self.count_jobs = [] # total count of jobs from all scraper threads
        self.df_jobs = pd.DataFrame() # placeholder for a Pandas DataFrame
        
        # how many pages to scrape?
        if all_pages:
            self.num_pages = 1
        else:
            self.num_pages = num_pages
        
        # for storing threads
        self.job_threads = [] # hold job scraping threads
        self.parse_threads = [] # hold job parsing threads

        self.lock = threading.Lock() # avoid race conditions
        
        
    ###############################
    # main program calls directly #
    ###############################
    def search_jobs(self):
        for i in range(len(self.job_search_terms)):
            self.job_threads.append(threading.Thread(target=self.get_glassdoor_jobs, 
                                                 args=(self.job_search_terms[i], self.location_search_terms[i])))
            self.job_threads[i].start()
            
            
    ###############################
    # main program calls directly #
    ###############################
    def parse_jobs(self):
        for i in range(len(self.job_search_terms)):
            self.parse_threads.append(threading.Thread(target=self.parse_glassdoor_jobs, 
                                                       args=(self.all_job_pages[i],i)))
            self.parse_threads[i].start()
    
    ######################################   
    # target for threads to get job data #
    ######################################
    def get_glassdoor_jobs(self, search_term, location_term):

        notification_blocked = False
        pages_searched = 0
        job_count = 0
        job_failures = 0
        job_pages = []
        page_count = 0

        # open website
        browser = webdriver.Chrome(chrome_options=chrome_options)
        browser.get('https://www.glassdoor.com/index.htm')

        # Enter search parameters
        search_job = browser.find_element_by_name('sc.keyword')  
        search_job.clear()
        time.sleep(1)
        search_job.send_keys(search_term)
        location = browser.find_element_by_id('LocationSearch')
        location.clear()
        time.sleep(1)
        location.send_keys(location_term)
        time.sleep(1)
        location.send_keys(Keys.RETURN)

        # get data from website
        while page_count < self.num_pages:

            pages_searched += 1

            time.sleep(3) # wait for new page to load

            jobs = browser.find_elements_by_class_name('jl')
            
            # get all jobs in a single page
            for job in jobs:
                try: 
                    if not notification_blocked:
                        try:
                            wait(browser, 3)
                            close_button = browser.find_element_by_class_name('mfp-close')
                            close_button.click()
                            notification_blocked = True
                        except:
                            pass

                    job.click()

                    time.sleep(2) # wait for job description to load

                    job_pages.append(browser.page_source) # data collection step
                        
                    job_count += 1
                except:
                    print("Issue clicking on job.")
                    job_failures += 1


            if pages_searched % 10 == 0:
                print("{0} - {1}: mined {2} jobs".format(search_term, location_term, job_count))

            if not all_pages:
                page_count += 1
                
            # get the next page of search results
            tries = 0
            for tries in range(5):
                try:
                    next_page = browser.find_element_by_class_name('next')
                    next_page.click()
                    break;
                except:
                    time.sleep(2)
                    pass
            else:
                break;

        browser.quit()
        
        with self.lock:
            self.count_jobs.append(job_count)
            self.all_job_pages.append(job_pages)
            title = "{} - {} | status: ENDED".format(search_term, location_term)
            print(title)
            print("="*len(title))
            print("Number of pages searched = {}".format(pages_searched))
            print("Number of jobs mined = {}".format(job_count))
            print("Number of failed job clicks = {}".format(job_failures))
            print("\n")
          
    ########################## 
    # target for job parsing #
    ##########################
    def parse_glassdoor_jobs(self, job_pages, index):
    
        data_dict = {"company":[], "position":[], "location":[], "link":[], "description":[]}
        count = 0
        # get some data from scraped web pages
        for job in job_pages:

            soup = BeautifulSoup(job, 'html.parser')

            link = soup.find('div', class_="regToApplyArrowBoxContainer").find('a', href=True)['href']
            if link:
                data_dict["link"].append("https://www.glassdoor.com{}".format(link))
            else:
                data_dict["link"].append("N/A")


            try:
                location = soup.find('div', class_="padLt padBot").findAll('span')
                if len(location) == 4:
                    data_dict["location"].append(location[3].text.split(' ' + chr(8211) + ' ')[1].strip())
                elif len(location) == 1:
                    data_dict["location"].append(location[0].text.split(' ' + chr(8211) + ' ')[1].strip())
            except:
                data_dict["location"].append("N/A")

                
            company = soup.find('a', class_="plain strong empDetailsLink")
            if company:    
                data_dict["company"].append(company.text.strip())
            else:
                data_dict["company"].append("N/A")

            position = soup.find('h1', class_="noMargTop noMargBot strong")
            if position:
                data_dict["position"].append(position.text.strip())
            else:
                data_dict["position"].append("N/A")

            description = soup.find('div', id='JobDescriptionContainer')
            if description:
                data_dict["description"].append(description.text.strip())
            else:
                data_dict["description"].append("N/A")

            count += 1

            if count % int(len(job_pages)/4) == 0:
                print("Job Search {0}: currently at job {1}".format(index+1,count))

        # package into DataFrame object
        df_tmp = pd.DataFrame.from_dict(data_dict)   

        # reorder columns in more logical way
        old_cols = df_tmp.columns.tolist()
        new_cols = ['position', 'company', 'location', 'description', 'link']
        if set(old_cols) == set(new_cols):
            df_tmp = df_tmp[new_cols]

        with self.lock:
            self.df_jobs = self.df_jobs.append(df_tmp, ignore_index=True)
        
        print("dataframe has been appended.")
    
    ###############################
    # main program calls directly #
    ###############################
    def save_jobs(self, save_location="./data/glassdoor-df-{}.csv".format(arrow.now().format('MM-DD-YYYY'))):
        if not self.df_jobs.empty:
            self.df_jobs.to_csv(save_location, index=False)
            print("Jobs data saved to {}.".format(save_location))
        else:
            print("Jobs DataFrame was empty and thus not saved to file.")
      
    
    
if __name__ == '__main__':
    
    job_terms = []
    location_terms = []
    
    if not sys.argv[1]:
        raise Exception('Need to provide a text file of search terms to scrape from. See documentation for details.')
    
    # get search parameters from file
    try:
        with open(sys.argv[1]) as file:
            job_searches = file.readlines()

            for job_search in job_searches:
                keywords = job_search.split("-")
                job_terms.append(keywords[0].strip())
                location_terms.append(keywords[1].strip())
    except:
        print("Issue reading {}. Be sure path is correct and format is correct. See documentation for details.".format(sys.argv[1]))
                
            
    scraper = glassdoor_scraper(job_search_terms=job_terms, location_search_terms=location_terms)
    
    # get job data from glassdoor
    scraper.search_jobs()
    for thread in scraper.job_threads:
        thread.join()
     
    # parse job data into Pandas DataFrame
    scraper.parse_jobs()
    for thread in scraper.parse_threads:
        thread.join()   
    
    print("\n")
    print("Total of {} jobs scraped.".format(np.sum(scraper.count_jobs)))      
    
    # save DataFrame to file
    scraper.save_jobs()
    
    print("\n")
    print("JOB SCRAPE IS COMPLETE!")