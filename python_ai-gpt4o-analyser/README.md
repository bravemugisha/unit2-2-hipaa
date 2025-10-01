# Overview

This folder contains a python file `main.py` that takes in a directory containing pdfs (`2-cases-database`) as well as a desired ouput csv such as `analyzed.csv`. The python script extracts text from each pdf sends it to the Chat GPT 4o AI for analysis, which returns information to answer the [track 1 google form](https://docs.google.com/forms/d/e/1FAIpQLSevmluOaUvUwCzhtOB9WIomytK9J3z9F4k29kiWEs31o8Q4bg/viewform?pli=1&pli=1). At the end of the analysis, the python script outputs a csv with the desired name containing all the structured respones such as `analyzed.csv`. 

Usage (please replace information within square brackets [...] with your own information): 

`python3 main.py [/path/to/input/folder] [output-filename].csv false`

Example: `Python3 main.py /Users/name/Desktop/hippa_doc_analysis/2-cases-database analyzed.csv false`

> It is important to set up an OpenAI api key to access the gpt-4o api
> Please create a `.env` file in this directory, and add your OpenAI api key as follows: 
> `OPENAI_API_KEY=replace-this-string-with-your-OpenAI-api-key`
> Nb: You can generate an OpenAI api key by visiting: https://platform.openai.com/docs/overview

# Installing Requirements

The python script uses PDF and RTF parsing libraries as well as the OpenAI SDK. 

The pdf-analysis folder contains all these dependencies to be run on MAC. However, it is non-standard to add venv folders to github so some issues might arise (especially if using Windows) and you might need to install the dependencies on your own machine as follows: 

Nb: Feel free to skip to this step 3 if you do not need a Python virtual environment  

1. Create a python virtual environment called `pdf-analysis` for instance. 

`python -m venv pdf-analysis`

2. Activate the virutal environment 

On mac/linux: `source pdf-analysis/bin/activate`
On Windows: `pdf-analysis\Scripts\activate`

3. Install the dependencies in the requirements.txt file 

`pip install -r requirements.txt`

# PDF files

Please add your own pdf directory if not already in this folder. 

