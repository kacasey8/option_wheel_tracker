from datetime import date

import numpy


# Counts stock open days between the two dates, assuming both end days are included
def busday_count_inclusive(start_date: date, end_date: date) -> int:
    if start_date == end_date:
        return 1
    return int(numpy.busday_count(start_date, end_date)) + 1
