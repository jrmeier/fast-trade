from datetime import datetime
import pandas as pd
import numpy as np
from pandas.core.base import DataError
from fast_trade.check_missing_dates import check_missing_dates


def test_check_missing_dates_none_missing():
    date_range = pd.date_range("2021-01-01", end="2021-02-01", freq="1T")

    mock_df = pd.DataFrame(np.random.randint(1, 20, (date_range.shape[0], 1)))
    mock_df.index = date_range

    perc_missinng, gaps = check_missing_dates(mock_df)

    assert perc_missinng == 0.0
    assert gaps.empty is True


# def test_check_missing_dates_some_missing():
#     date_range = list(pd.date_range("2021-01-01", end="2021-02-01", freq="2T"))
#     print("daterange len: ", len(date_range))

#     removed_dates = []

#     # removed_dates.append(date_range.pop(6))
#     # removed_dates.append(date_range.pop(7))
#     # removed_dates.append(date_range.pop(8))

#     mock_df = pd.DataFrame(
#         np.random.randint(1, 20, (len(date_range), 1)), index=date_range
#     )

#     # remove_dates = date_range[3:5]

#     # print(remove_date)

#     # to_delete = ['2020-02-17', '2020-02-18']
#     # sp[~(sp.index.strftime('%Y-%m-%d').isin(to_delete))]

#     # mock_df = mock_df[~mock_df.index.isin(remove_dates)]
#     # mock_df = mock_df.drop(remove_dates)
#     # mock_df = mock_df.asfreq("2T")
#     # print("missing_dates: ", missing_dates)

#     # mock_df = mock_df[mock_df.index not in remove_dates]
#     # df[~df.date.between(date1, date2)] – piRSq
#     # mock_df = mock_df[~mock_df.between("2021-01-10", "2021-01-11")]
#     # df_filtered = df[df['Age'] >= 25] .
#     # mock_df = mock_df[~mock_df[ > 10]

#     # mock_df.resample("2T")

#     perc_missinng, gaps = check_missing_dates(mock_df)

#     assert perc_missinng == 0.0
#     assert gaps.empty is False
