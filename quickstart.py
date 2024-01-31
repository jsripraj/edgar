import os.path
from datetime import date, timedelta
import pprint
import json

import requests
from bs4 import BeautifulSoup

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from openai import OpenAI
from polygon import RESTClient
from sec_cik_mapper import StockMapper

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
# CIK = 1637207 # PLNT
# CIK = 12659 # HRB
# CIK = 1498710 # SAVE
# CIK = 320193 # AAPL
# CIK = 1543151 # UBER
USER_EMAIL = 'jsripraj@gmail.com'
ASSET_CUTOFF_PERCENTAGE = 0.05


class Filing:
  def __init__(self, end: date, accn: str, fy: int, fp: str, form: str, filed: date):
    self.end = end 
    self.accn = accn  
    self.fy = fy
    self.fp = fp
    self.form = form
    self.filed = filed
    self.financial_data = {}
  
  def __str__(self):
    out = (
      'Filing Object\n'
      f'  end: {self.end}\n'
      f'  accn: {self.accn}\n'
      f'  fy: {self.fy}\n'
      f'  fp: {self.fp}\n'
      f'  form: {self.form}\n'
      f'  filed: {self.filed}\n'
    )
    return out
  

def main():
  """ 
  Run trading robot.
  """
  # tickers = ['AAPL'] # Eventually this will be a list of every ticker on the market
  tickers = get_tickers()
  for ticker in tickers:
    cik = get_cik(ticker)
    market_cap = get_market_cap(ticker)
    data = edgar_get_data(cik)
    filings = edgar_get_filings(data)
    populate_earnings(data, filings)

    try:
      earnings22 = float((get_filing_by_year(filings, 2022)).financial_data['earnings'])
      pe = float(market_cap) / earnings22
    except KeyError:
      earnings22 = 'Error'
      pe = 'Error'
    print(f'Ticker: {ticker}, CIK: {cik}, Cap: {market_cap}, Earnings: {earnings22}, PE: {pe}')


  """ GOOGLE SHEETS STUFF
  creds = None
  # The file token.json stores the user's access and refresh tokens, and is
  # created automatically when the authorization flow completes for the first
  # time.
  if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
  # If there are no (valid) credentials available, let the user log in.
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      flow = InstalledAppFlow.from_client_secrets_file(
          "desktop_credentials.json", SCOPES
      )
      creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open("token.json", "w") as token:
      token.write(creds.to_json())
  """

  # try:
    # service = build("sheets", "v4", credentials=creds)
    # spreadsheet_id = create_spreadsheet("test-report", service)
    # create_sheets(spreadsheet_id, service)
    # company_data = edgar_get_company_metadata()
    # ticker = company_data['tickers'][0]

    # test_polygon(ticker)
    # assets = get_assets(data, filings)
    # line_items = filter_line_items(data, filings, assets)
    # pprint.pprint(line_items)
    # print(f'len of filtered line items = {len(line_items)}')
    # print(*filings, sep="\n")
    # test_chatgpt(line_items)
    # # Pass: spreadsheet_id,  range_name, value_input_option, _values, and service
    # update_values(
    #     spreadsheet_id,
    #     "A1",
    #     "USER_ENTERED",
    #     [data],
    #     service
    # )
  # except HttpError as err:
  #   print(err)


def populate_earnings(data, filings) -> None:
  """
  Stores the integer earnings (net income) value in the corresponding Filing.
  """
  # print(list(data['facts'].keys()))
  # print(str(data).replace("'", '"'))
  # year = 2022
  # filing = get_filing_by_year(filings, year)
  line_items = data['facts']['us-gaap']

  # Get the actual name of the line item
  search_term = 'NetIncomeLoss'
  for name in line_items.keys():
    # For more complicated searches, may have to use FuzzyWuzzy
    if search_term in name:
      item_name = name
      break

  i = 0 # points to a Filing in filings
  raw_item_filings = line_items[item_name]['units']['USD']
  for raw_item_filing in raw_item_filings:
    filing = filings[i]
    if raw_item_filing['accn'] == filing.accn and raw_item_filing['end'] == str(filing.end):
      filing.financial_data['earnings'] = int(raw_item_filing['val'])
      i += 1
      if i >= len(filings):
        break
  return 

  #       val = get_item_value_at_filing(data, name, filing)
  #       # if not val:
  #       #   continue
  #       # print(f"Name: {name}")
  #       # print(f"Label: {items[name]['label']}")
  #       # print(f"Value: {val}\n")
  #       # print(f"Description: {items[name]['description']}")
  #       return val


# def get_item_value_at_filing(data: dict, item_name: str, filing: Filing) -> (int | None):
#   """
#   Returns the value of the given item_name for the given Filing.
#   Returns None if no value is found.
#   """
#   if not filing:
#     print(f'No filing found.')
#     return None
#   items = data['facts']['us-gaap']
#   # pprint.pprint(items['Assets']['units']['USD'])
#   if 'USD' in items[item_name]['units']:
#     item_filings = items[item_name]['units']['USD']
#     for item_filing in item_filings:
#       if item_filing['accn'] == filing.accn and item_filing['end'] == str(filing.end):
#         res = int(item_filing['val'])
#         # print(res)
#         return res
#   return None


def get_market_cap(ticker: str) -> int:
  """
  Returns the market cap of the given ticker. This function gets market cap 
  data by scraping Yahoo Finance with BeautifulSoup.
  """
  try:
    url = f"https://finance.yahoo.com/quote/{ticker}"
    r = requests.get(url)
    # print(r.text)
    soup = BeautifulSoup(r.text, 'html.parser')
    # print(soup.prettify())
    # res = soup.find(string="Market Cap")
    # print(res.parent.parent.next_sibling)
    res = soup.find(attrs={"data-test":"MARKET_CAP-value"}) # example res.string = '6.192B'
    num = float(res.string[:-1])
    multipliers = {
      'T': pow(10, 12),
      'B': pow(10, 9),
      'M': pow(10, 6)
    }
    mult = multipliers[res.string[-1]]
    cap = int(num * mult)
    return cap
  except HttpError as error:
    print(f"An error occurred: {error}")
    return error


def get_tickers() -> list:
  """
  Returns a sorted list of all common stock tickers trading on the NYSE and the NASDAQ.
  """
  # exchange_code = 'US'
  security_type = 'common_stock'
  exchanges = ['NYSE', 'NASDAQ']
  tickers = set()
  for exchange in exchanges:
    url = f'https://eodhd.com/api/exchange-symbol-list/{exchange}?type={security_type}&api_token=65b5850a9df356.73179775&fmt=json'
    data = requests.get(url).json()
    for stock in data:
      tickers.add(stock['Code'])
  tickers = sorted(list(tickers))
  return tickers
    # print(type(data))
    # first = data[0]
    # print(first)
    # print(type(first))


  # pprint.pprint(data)


def get_cik(ticker: str):
  """
  Returns the CIK corresponding to the given ticker
  """
  mapper = StockMapper()
  cik = mapper.ticker_to_cik[ticker]
  return format_cik(cik)


def test_polygon(ticker):
  with open('polygon_key.txt') as f:
    key = f.read().strip()
  client = RESTClient(api_key=key)
  # url = f'https://api.polygon.io/v1/open-close/{ticker}/{date.today()}?adjusted=true&apiKey={key}'
  # print(f'url = {url}')
  # headers = {'user-agent': USER_EMAIL}
  try:
    for t in client.list_tickers(market="stocks", type="CS", active=True):
      print(t)
    # r = requests.get(url)
    # yesterday = date.today() - timedelta(days=1)
    # r = client.get_previous_close_agg(ticker)
    # pprint.pprint(vars(r[0]))
    # json_data = r.json()
    # pprint.pprint(json_data)
    # return json_data
  except HttpError as error:
    print(f"An error occurred: {error}")
    return error


def test_chatgpt(items):
  print('testing chatgpt')
  client = OpenAI()
  
  # test_entries = [
  #   "AccountsPayableCurrent",
  #   "AccountsPayableRelatedPartiesCurrent",
  #   "AccountsPayableRelatedPartiesCurrentAndNoncurrent",
  #   "AccountsPayableRelatedPartiesNoncurrent",
  #   "AccountsReceivableNetCurrent",
  #   "AccountsReceivableRelatedParties",
  #   "AccountsReceivableRelatedPartiesCurrent",
  #   "AccretionAmortizationOfDiscountsAndPremiumsInvestments",
  #   "AccruedLiabilitiesCurrent",
  # ]

  completion = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
      {"role": "user", "content": "I will give you a list of financial statement line items"
        "For each of the items, tell me whether an increase is good, bad, or neutral."
       f"Here is the list: {str(items)}"}
    ]
  )
  resp = completion.choices[0].message.content
  pprint.pprint(resp)
  
  # print(f'len of items is {len(str(items))}')
  # completion = client.chat.completions.create(
  #   model="gpt-3.5-turbo",
  #   messages=[
  #     {"role": "user", "content": "I will give you a list of financial statement line items"
  #      "First, list the items that belong in the Balance Sheet. "
  #      "Second, list the items that belong in the Income Statement. "
  #      "Third, list the items that belong in the Cash Flow Statement. "
  #      f"Here is the list: {str(items)}"}
  #   ]
  # )
  # resp = completion.choices[0].message.content
  # balance_items, income_items, cash_items = resp.split('\n\n')
  # completion = client.chat.completions.create(
  #   model="gpt-3.5-turbo",
  #   messages=[
  #     {"role": "user", 
  #      "content": "I will give you a list of some balance sheet line items."
  #      "Organize them into a typical balance sheet order."
  #      f"Here is the list: {balance_items}"
  #     }
  #   ]
  # )
  # resp = completion.choices[0].message.content
  # print(resp)
  # print(f'resp split into {len(resp)} pieces')
  # for i in range(len(resp)):
  #   print(f'Piece #{i}:\n{resp[i]}\n')


def create_spreadsheet(title, service):
  """
  Creates the Sheet the user has access to.
  Load pre-authorized user credentials from the environment.
  TODO(developer) - See https://developers.google.com/identity
  for guides on implementing OAuth2 for the application.
  """
  # pylint: disable=maybe-no-member
  try:
    spreadsheet = {"properties": {"title": title}}
    spreadsheet = (
        service.spreadsheets()
        .create(body=spreadsheet, fields="spreadsheetId")
        .execute()
    )
    # print(f"Spreadsheet ID: {(spreadsheet.get('spreadsheetId'))}")
    return spreadsheet.get("spreadsheetId")
  except HttpError as error:
    print(f"An error occurred: {error}")
    return error
    

def create_sheets(spreadsheet_id, service):
  requests = []
  requests.append(
    {
      "updateSheetProperties": {
        "properties": {
          "sheetId": 0,
          "title": "Balance Sheet"
        },
        "fields": "title",
      }
    }
  )
  requests.append(
    {
      "addSheet": {
        "properties": {
          "title": "Income Statement"
        }
      }
    }
  )
  requests.append(
    {
      "addSheet": {
        "properties": {
          "title": "Cash Flow Statement"
        }
      }
    }
  )
  
  body = {"requests": requests}
  response = (
    service.spreadsheets()
    .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
    .execute()
  )
  return response


def edgar_get_data(cik: str) -> dict:
  """
  Returns company data obtained from EDGAR.
  """
  url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
  headers = {'user-agent': USER_EMAIL}
  try:
    r = requests.get(url, headers=headers)
    json_data = r.json()
    return json_data
  except HttpError as error:
    print(f"An error occurred: {error}")
    return error


def edgar_get_company_metadata():
  """
  Returns dictionary of company metadata from EDGAR
  """
  url = f'https://data.sec.gov/submissions/CIK{format_CIK(CIK)}.json'
  headers = {'user-agent': USER_EMAIL}
  try:
    r = requests.get(url, headers=headers)
    json_data = r.json()
    # print(json.dumps(json_data))
    return json_data
  except HttpError as error:
    print(f"An error occurred: {error}")
    return error


def edgar_get_filings(data: dict) -> list[Filing]:
  """
  Returns a chronological list of FYE Filings. The last element in the list 
  is the most recent partial year Filing, if applicable.
  """
  filings = data["facts"]["us-gaap"]["Assets"]["units"]["USD"]
  output = []
  for f in filings:
    if f['fp'] == 'FY':
      end_date = edgar_date_string_to_date(f['end'])
      filed_date = edgar_date_string_to_date(f['filed'])
      # Make sure fiscal year makes sense and time to file is less than half a year 
      if f['fy'] <= end_date.year and (filed_date - end_date).days < 180:
        output.append(Filing(end_date, f['accn'], int(f['fy']), f['fp'], f['form'], filed_date))
  # Append the most recent partial year Filing, if applicable
  if filings[-1]["fp"] != "FY":
    output.append(Filing(end_date, f['accn'], int(f['fy']), f['fp'], f['form'], filed_date))
  return output


def get_assets(data, filings):
  """
  Returns the value of Assets from the most recent fiscal year. 
  Assets will be used to calculate a cutoff to filter out less material financial items.
  """
  if filings[-1].fy == 'FY':
    i = -1
  else:
    i = -2
  asset_filings = data["facts"]["us-gaap"]["Assets"]["units"]["USD"]
  for asset_filing in asset_filings:
    accn = asset_filing['accn']
    end = edgar_date_string_to_date(asset_filing['end'])
    if accn == filings[i].accn and end == filings[i].end:
      return int(asset_filing['val'])


def filter_line_items(data, filings, assets):
  """
  Returns a list of line item names, excluding any items that are not able, in any
  filing, to meet a given percentage of assets.
  """
  output = []
  line_items = data['facts']['us-gaap']
  for name in line_items.keys():
    if "USD" in line_items[name]["units"]:
      for new_filing in line_items[name]["units"]["USD"]:
        # print(f'new_filing = {new_filing}')
        filing = get_filing_by_accn(filings, new_filing['accn'])
        if filing and new_filing['end'] == f'{filing.end}':
          if float(new_filing['val'] >= ASSET_CUTOFF_PERCENTAGE * assets):
            output.append(line_items[name]["label"])
            # print(name)
            # print(f'Label: {line_items[name]["label"]}')
            # print(f'Description: {line_items[name]["description"]}\n')
            break
  return output


def get_filing_by_accn(filings, accn):
  """
  Returns the Filings object with the given accn.
  If no matching Filing is found, returns None.
  """
  for f in filings:
    if f.accn == accn:
      return f
  return None


def get_filing_by_year(filings, year):
  """
  Returns the Filing object for the given year.
  If no matching Filing is found, returns None.
  """
  for f in filings:
    if f.end.year == year:
      return f
  return None


def format_cik(cik):
  """
  Returns a 10-digit string representation of a given CIK.
  """
  cik = str(cik)
  out = ('0' * (10 - len(cik))) + cik
  return out
  

def edgar_date_string_to_date(date_str):
  """
  Takes a date string in the form yyyy-mm-dd (such as those obtained from the
  EDGAR API) and returns a Python date object.
  """
  d = [int(x) for x in date_str.split('-')]
  return date(d[0], d[1], d[2])


def update_values(spreadsheet_id, range_name, value_input_option, _values, service):
  """
  Creates the batch_update the user has access to.
  Load pre-authorized user credentials from the environment.
  TODO(developer) - See https://developers.google.com/identity
  for guides on implementing OAuth2 for the application.
  """
  # creds, _ = google.auth.default()
  # pylint: disable=maybe-no-member
  try:
    body = {"values": _values}
    result = (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption=value_input_option,
            body=body,
        )
        .execute()
    )
    print(f"{result.get('updatedCells')} cells updated.")
    return result
  except HttpError as error:
    print(f"An error occurred: {error}")
    return error


if __name__ == "__main__":
  main()