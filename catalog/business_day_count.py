import pandas
from pandas.tseries.holiday import USFederalHolidayCalendar

# Counts stock open days between the two dates, assuming both
# end days are included
def busday_count_inclusive(start_date, end_date):
  C = pandas.offsets.CustomBusinessDay(calendar=USFederalHolidayCalendar())
  if (start_date == end_date):
  	return 1
  pandas_result = (pandas.DataFrame(index=pandas.to_datetime([start_date, end_date]))
      .resample(C, closed='right') 
      .asfreq()
      .index
      .size)
  
  return pandas_result