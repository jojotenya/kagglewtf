import pandas as pd
from util import *
import re
from datetime import datetime
import pickle
file_path = '/data/examples/trend/data/'
rawdata_path = file_path + 'query_log/'

############ etl ############
def norm_it(df):
    df = df.div(df.sum(axis=1), axis=0)
    return df

def percentile(n):
    def percentile_(x):
        return np.percentile(x, n)
    percentile_.__name__ = 'percentile_%s' % n
    return percentile_

flags = ['size','sum','mean','std','max','min','median','skew','mad',percentile(25),percentile(75)]
flags = ['mean','std','max','min','median','skew','mad',percentile(25),percentile(75)]
def get_aggr(df,flags=flags):
    df = df.groupby(df.index.get_level_values(0)).agg(flags)
    df = df.fillna(0)
    return df

def df_add(df,df_past,add_by='int'):
    intersect_ix = df.index.intersection(df_past.index)
    diff_ix = df.index.difference(df_past.index)
    diff_ix_past = df_past.index.difference(df.index)
    if add_by == 'int':
        df0 = df.ix[intersect_ix].add(df_past.ix[intersect_ix])
    elif add_by == 'corpus':
        df0 = df.ix[intersect_ix] + ' ' + df_past.ix[intersect_ix]
    df1 = df.ix[diff_ix]
    df2 = df_past.ix[diff_ix_past]
    df = pd.concat([df0,df1,df2],axis=0)
    return df
    
def clean_df(df):
    df['ProductID'] = df['ProductID'].astype('str')
    df = df.replace(['055649'],['55649'])
    return df

def append_list(x):
    new_x = x.dropna()
    if new_x.shape[0] == 0:
        return
    elif new_x.shape[0] == 1:
        new_x = new_x.values[0]
    else:
        new_x = np.append(np.array(list(new_x[0])),np.array(list(new_x[1])))
    new_x = set(new_x)
    return new_x

def get_train_test_intersect(df,df_past=None):
    if 'FileID' in df.columns:
        df = df.set_index('FileID')
    test_ids = pd.read_csv(file_path+'testing-set.csv',header=None)
    test_ids = pd.Index(test_ids[0])
    train_ids = pd.read_csv(file_path+'training-set.csv',header=None)
    train_ids = pd.Index(train_ids[0])
    df_train = df.ix[train_ids].dropna()
    df_test = df.ix[test_ids].dropna()
    #uniq product
    train_prod_set = set(df_train['ProductID'])
    test_prod_set = set(df_test['ProductID'])
    #uniq customer
    train_cus_set = set(df_train['CustomerID'])
    test_cus_set = set(df_test['CustomerID'])
    #uniq prod cross customer
    train_prod_cus_set = df_train.groupby('ProductID')['CustomerID'].unique()
    test_prod_cus_set = df_test.groupby('ProductID')['CustomerID'].unique()
    if df_past is not None:
        #merge prod
        train_prod_set.update(df_past['train_prod_set'])
        test_prod_set.update(df_past['test_prod_set'])

        #merge customer
        train_cus_set.update(df_past['train_cus_set'])
        test_cus_set.update(df_past['test_cus_set'])

        #merge prod cross customer
        train_prod_cus_set = df_train.groupby('ProductID')['CustomerID'].unique()
        train_prod_cus_set = pd.concat([train_prod_cus_set,df_past['train_prod_cus_set']],axis=1)
        train_prod_cus_set.columns = [0,1]
        print(train_prod_cus_set.head())
        train_prod_cus_set = train_prod_cus_set.apply(append_list,axis=1)

        test_prod_cus_set = df_test.groupby('ProductID')['CustomerID'].unique()
        test_prod_cus_set = pd.concat([test_prod_cus_set,df_past['test_prod_cus_set']],axis=1)
        test_prod_cus_set.columns = [0,1]
        test_prod_cus_set = test_prod_cus_set.apply(append_list,axis=1)

    return {'train_prod_set':train_prod_set,'test_prod_set':test_prod_set,
           'train_cus_set':train_cus_set,'test_cus_set':test_cus_set,
           'train_prod_cus_set':train_prod_cus_set,'test_prod_cus_set':test_prod_cus_set}

def merge_prod_cus(df,dump=True):
    #merge cus
    cus_set = df['train_cus_set']
    test_cus_set = df['test_cus_set']
    cus_set.update(test_cus_set)
    #merge prod
    prod_set = df['train_prod_set']
    test_prod_set = df['test_prod_set']
    prod_set.update(test_prod_set)
    #merge prod cross cus
    train_prod_cus = df['train_prod_cus_set']
    test_prod_cus = df['test_prod_cus_set']
    df_prod_cus = pd.concat([train_prod_cus,test_prod_cus],join='inner',axis=1)
    df_prod_cus = df_prod_cus.apply(append_list,axis=1)
    if dump:
        pickle.dump(cus_set, 'export/trend_common_customers.pkl')
        pickle.dump(prod_set, 'export/trend_common_products.pkl')
        pickle.dump(df_prod_cus, 'export/trend_common_products_customers.pkl')
    return {'cus_set':cus_set,'prod_set':prod_set,'df_prod_cus':df_prod_cus}

def common_prod_cus_filter(df,df_prod_cus):
    prods = df_prod_cus.index
    if len(prods) == 0: return df
    if df.index.name == 'FileID': df = df.reset_index()
    df = df.set_index('ProductID')
    df = df.ix[prods]
    dfs = []
    for i,prod in enumerate(prods):
        #get customers of certain product
        cus = pd.Index(df_prod_cus.ix[prod])
        #get certain product of df
        dft = df.ix[prod].dropna()
        dft = dft.reset_index()
        print(dft.head(2))
        dft = dft.set_index('CustomerID')
        dft = dft.ix[cus].dropna()
        dft = dft.reset_index()
        dfs.append(dft)
    df = pd.concat(dfs,axis=0)
    df['QueryTs'] = df['QueryTs'].astype(int)
    df = df.reset_index()
    return df

def common_filter(df,df_target,typ='prod_cus'):
    if df.index.name == 'FileID': df = df.reset_index()
    if typ == 'prod_cus':
        df = common_prod_cus_filter(df,df_target['df_%s'%typ])
    else:
        target_set = df_target['%s_set'%typ]
        ixs = pd.Index(target_set)
        if typ == 'prod':
            df = df.set_index('ProductID')
        elif typ == 'cus':
            df = df.set_index('CustomerID')
        df = df.ix[ixs]
        df = df.reset_index()
    return df

#FileID被各個ProductID開啟的次數的比例
def get_file_product_count_percentage(df,df_perc=None,normalize=False):
    dft = df[['FileID','ProductID']]
    dft = dft.assign(Count=1)
    dft = dft.groupby(['FileID','ProductID'],as_index = False).sum().pivot('FileID','ProductID').fillna(0)
    if normalize:
        dft = dft.div(dft.sum(axis=1), axis=0)
    cols = [col+'_count_percentage' for col in list(dft.columns.get_level_values(1))]
    dft.columns = cols
    if df_perc is not None:
        intersect_ix = dft.index.intersection(df_perc.index)
        diff_ix = dft.index.difference(df_perc.index)
        diff_ix_perc = df_perc.index.difference(dft.index)
        df0 = dft.ix[intersect_ix].add(df_perc.ix[intersect_ix])
        df1 = dft.ix[diff_ix]
        df2 = df_perc.ix[diff_ix_perc]
        dft = pd.concat([df0,df1,df2],axis=0)
        '''
        rows = set(df_perc.index) - set(dft.index)
        for row in rows:
            dft.ix[row] = 0
        rows = set(dft.index) - set(df_perc.index)
        for row in rows:
            df_perc.ix[row] = 0
        dft = dft.add(df_perc)
        '''
    return dft

def get_file_product_count(df,df_perc=None,normalize=False):
    dft = df[['FileID','ProductID']]
    dft = dft.assign(Count=1)
    dft = dft.groupby(['FileID','ProductID'],as_index = False).sum().pivot('FileID','ProductID').fillna(0)
    if normalize:
        dft = dft.div(dft.sum(axis=1), axis=0)
    cols = [col for col in list(dft.columns.get_level_values(1))]
    dft.columns = cols
    if df_perc is not None:
        dft = df_perc.append(dft)
    return dft

#每次被開啟的間隔時間的mean/std
def get_open_time(df,df_interval=None,max_timestamp=None):
    dft = df[['FileID','QueryTs']]
    if max_timestamp is not None:
        dft = dft.set_index('FileID')
        dft = pd.concat([pd.DataFrame(max_timestamp),dft],axis=0)
        dft = dft.reset_index()
    dft = dft.sort_values(by=['QueryTs'])
    dft['QueryTsInterval'] = dft.groupby('FileID')['QueryTs'].transform(pd.Series.diff)
    dft = dft.dropna()
    if df_interval is not None:
        dft = pd.concat([df_interval,dft],axis=0)
    max_timestamp = dft.groupby('FileID')['QueryTs'].max()
    return dft, max_timestamp

def get_open_time(df,df_past=None):
    df = df[['FileID','QueryTs']]
    if df_past is not None and df_past['max_timestamp'] is not None:
        df = df.set_index('FileID')
        df = pd.concat([pd.DataFrame(df_past['max_timestamp']),df],axis=0)
        df = df.reset_index()
    df = df.sort_values(by=['QueryTs'])
    df['QueryTsInterval'] = df.groupby('FileID')['QueryTs'].transform(pd.Series.diff)
    df = df.dropna()
    if df_past is not None and df_past['df'] is not None:
        df = pd.concat([df_past['df'],df],axis=0)
    max_timestamp = df.groupby('FileID')['QueryTs'].max()
    return {'df':df, 'max_timestamp':max_timestamp}

def get_field_open_time(df,df_past=None,field='CustomerID'):
    df = df[['FileID',field,'QueryTs']]
    if df_past is not None and df_past['max_timestamp'] is not None:
        df = df.set_index('FileID')
        df = pd.concat([pd.DataFrame(df_past['max_timestamp']).reset_index().set_index('FileID'),df],axis=0)
        df = df.reset_index()
    df = df.sort_values(by=['QueryTs'])
    df['QueryTsInterval%s'%field] = df.groupby(['FileID',field])['QueryTs'].transform(pd.Series.diff)
    df = df.dropna()
    if df_past is not None and df_past['df'] is not None:
        df = pd.concat([df_past['df'],df],axis=0)
    max_timestamp = df.groupby(['FileID',field])['QueryTs'].max()
    return {'df':df, 'max_timestamp':max_timestamp}

flags = ['mean','std','count','size','nunique','max','min','median','sum','skew','mad']
flags = ['mean','std','count','nunique','max','min','median','sum','skew','mad',percentile(25),percentile(75)]
def get_open_time_aggr(df,field='',flags=flags):
    #q1 = df.groupby('FileID')['QueryTsInterval'].quantile(0.25)
    #q1.name = 'QueryTsIntervalQ1'
    #q3 = df.groupby('FileID')['QueryTsInterval'].quantile(0.75)
    #q3.name = 'QueryTsIntervalQ3'
    df = df.groupby('FileID')['QueryTsInterval%s'%field].agg(flags)
    cols = df.columns
    cols = [col.capitalize() for col in cols]
    cols = ['QueryTsInterval%s%s'%(col,field) for col in cols]
    df.columns = cols
    #df = pd.concat([df,q1,q3],axis=1)
    df = df.fillna(0)
    return df

#tfidf
def cal_tfidf(df,field):
    vectorizer = TfidfVectorizer()
    tfidf = vectorizer.fit_transform(df)
    tfidf = tfidf.toarray()
    fileIds=vectorizer.get_feature_names()
    #tfidf_sum = np.sum(tfidf,axis=0)
    tfidf_mean = np.mean(tfidf,axis=0)
    tfidf_median = np.median(tfidf,axis=0)
    tfidf_std = np.std(tfidf,axis=0)
    tfidf_min = np.amin(tfidf,axis=0)
    tfidf_max = np.amax(tfidf,axis=0)
    tfidf_ptp = np.ptp(tfidf,axis=0)
    tfidf_q1 = np.percentile(tfidf,25,axis=0)
    tfidf_q3 = np.percentile(tfidf,75,axis=0)
    idf = vectorizer.idf_
    df = pd.DataFrame({'FileID':fileIds,'%s_tfidf_mean'%field:tfidf_mean,'%s_tfidf_median'%field:tfidf_median,
                      '%s_tfidf_std'%field:tfidf_std,'%s_tfidf_min'%field:tfidf_min,'%s_tfidf_max'%field:tfidf_max,
                      '%s_tfidf_ptp'%field:tfidf_ptp,'%s_tfidf_q1'%field:tfidf_q1,'%s_tfidf_q3'%field:tfidf_q3,'%s_idf'%field:idf})

    df = df.set_index('FileID')
    return df

def cal_tfidf(df,field):
    vectorizer = TfidfVectorizer()
    tfidf = vectorizer.fit_transform(df)
    tfidf = tfidf.toarray()
    fileIds=vectorizer.get_feature_names()
    idf = vectorizer.idf_
    #tfidf_sum = np.sum(tfidf,axis=0)
    tfidf_mean = []
    tfidf_median = [] 
    tfidf_std = [] 
    tfidf_min = []
    tfidf_max = []
    tfidf_ptp = []
    tfidf_q1  = []
    tfidf_q3  = []
    for t in tfidf.T:
        tfidf_mean.append(np.mean(t))
        tfidf_median.append(np.median(t))
        tfidf_std.append(np.std(t))
        tfidf_min.append(np.amin(t))
        tfidf_max.append(np.amax(t))
        tfidf_ptp.append(np.ptp(t))
        tfidf_q1.append(np.percentile(t,25))
        tfidf_q3.append(np.percentile(tf,75))
    
    df = pd.DataFrame({'FileID':fileIds,'%s_tfidf_mean'%field:tfidf_mean,'%s_tfidf_median'%field:tfidf_median,
                      '%s_tfidf_std'%field:tfidf_std,'%s_tfidf_min'%field:tfidf_min,'%s_tfidf_max'%field:tfidf_max,
                      '%s_tfidf_ptp'%field:tfidf_ptp,'%s_tfidf_q1'%field:tfidf_q1,'%s_tfidf_q3'%field:tfidf_q3,'%s_idf'%field:idf})

    df = df.set_index('FileID')
    return df

def get_corpus(df,df_past=None,field='CustomerID'):
    df = df.groupby(field).apply(get_list_FileID)
    if df_past is not None:
        intersect_ix = df.index.intersection(df_past.index)
        diff_ix = df.index.difference(df_past.index)
        diff_ix_past = df_past.index.difference(df.index)
        df0 = df.ix[intersect_ix] + ' ' + df_past.ix[intersect_ix]
        df1 = df.ix[diff_ix]
        df2 = df_past.ix[diff_ix_past]
        df = pd.concat([df0,df1,df2],axis=0)
    return df

#uniq count
def concat_list(x):
    return list(x[0])+list(x[1])

def count_uniq(x):
    return len(x[0])

def get_uniq(df,df_past=None,field='uniqCustomer'):
    #filed : 'uniqCustomer' , 'uniqProduct'
    if 'Customer' in field:
        df = df.groupby('FileID')['CustomerID'].unique()
    elif 'Product' in field:
        df = df.groupby('FileID')['ProductID'].unique()
    elif 'Product' in field and 'Customer' in field:
        df = df.assign(ProductCustomerID=df['ProductID'].astype('str')+df['CustomerID'].astype('str'))
        df = df.drop(['ProductID','CustomerID'])
        df = df.groupby('FileID')['ProductCustomerID'].unique()
    df.name = field
    ixs = df.index
    df = pd.DataFrame(df)
    df = get_nuniq(df,field=field)
    df = pd.DataFrame(df)
    if df_past is not None:
        #df  = pd.DataFrame({0:df.values,1:df_past.values})
        #df = df.apply(concat_list,axis=1)
        #df.index = ixs
        df = pd.concat([df_past,df],axis=0)
        #df.name = field
    return df

def get_nuniq(df,field='uniqCustomer'):
    df = df.groupby(df.index.get_level_values(0))[field].apply(count_uniq)
    return df

#count
def get_count(df,df_past=None,field='countCustomer'):
    #filed : 'countCustomer' , 'countProduct'
    if 'Customer' in field:
        df = df.groupby('FileID')['CustomerID'].count()
    elif 'Product' in field:
        df = df.groupby('FileID')['ProductID'].count()
    elif 'Product' in field and 'Customer' in field:
        df = df.assign(ProductCustomerID=df['ProductID'].astype('str')+df['CustomerID'].astype('str'))
        df = df.drop(['ProductID','CustomerID'])
        df = df.groupby('FileID')['ProductCustomerID'].count()
    df.name = field
    df = pd.DataFrame(df)
    if df_past is not None:
        #df = df_add(df,df_past)
        df = df_past.append(df)
    df.name = field
    return df

def get_daily_count(df,df_past=None):
    df = df.groupby('FileID')['FileID'].count()
    df.name = 'FileIDCountDaily'
    df = pd.DataFrame(df)
    if df_past is not None:
        df = df_past.append(df) 
    df = pd.DataFrame(df)
    return df

#datetime
def get_datetime(ts,fields=['hour','weekday']):
    dt = datetime.fromtimestamp(ts)
    dt_dict = {}
    for field in fields:
        if field == 'hour':
            dt_dict[field] = dt.hour
        elif field == 'weekday':
            dt_dict[field] = dt.weekday()
    return dt_dict

def get_hour(ts):
    return get_datetime(ts,['hour'])['hour']

def get_weekday(ts):
    return get_datetime(ts,['weekday'])['weekday']

def get_hour_df(df,df_past=None):
    df = df.set_index('FileID')
    df_hour = df['QueryTs'].apply(get_hour)
    df_hour.name = 'hour'
    df_hour = pd.DataFrame(df_hour)
    df_hour = pd.get_dummies(df_hour.hour)
    df_hour = df_hour.groupby(df_hour.index.get_level_values(0)).sum()
    cols = df_hour.columns
    cols = ['hour%s'%str(c) for c in cols]
    df_hour.columns = cols
    if df_past is not None:
        df_hour = df_past.append(df_hour)
    return df_hour

def get_week_df(df,df_past=None):
    if 'FileID' in df.columns:
        df = df.set_index('FileID')
    df = df['QueryTs'].apply(get_weekday)
    df.name = 'weekday'
    df = pd.DataFrame(df)
    df = pd.get_dummies(df.weekday)
    df = df.groupby(df.index.get_level_values(0)).sum()
    cols = df.columns
    cols = ['week%s'%str(c) for c in cols]
    df.columns = cols
    if df_past is not None:
        df = df_past.append(df)
    return df

def get_norm_df(df,read_file=None): 
    if read_file:
        df = pd.read_csv('export/%s.csv'%read_file)
    if 'FileID' in df.columns:
        df= df.set_index('FileID')
    cols = []
    for k,v in df.iteritems():
        if 'sum' in k:
            cols.append(k)
    if len(cols) == 0:
        cols = []
        for k,v in df.iteritems():
            if 'mean' in k:
                cols.append(k)
        df_norm = norm_it(df[cols])
        cols = df_norm.columns
        cols = [re.sub('mean','percentage',col) for col in cols]
    else:
        df_norm = norm_it(df[cols])
        cols = df_norm.columns
        cols = [re.sub('sum','percentage',col) for col in cols]
    df_norm.columns = cols
    df = pd.concat([df,df_norm],axis=1)
    return df
   
def extend_cols(df):
    i0 = df.columns.get_level_values(0)
    i1 = df.columns.get_level_values(1)
    cols = ['%s_%s'%(x[0],x[1]) for x in zip(i0,i1)]
    df.columns = cols
    return df
  
############ etl ############

############ model ############
def get_data(version=4):
    cols = ['FileID','y']
    df = pd.read_csv('export/trend_v%s.csv'%version)
    df = df.set_index('FileID')
    test = pd.read_csv(file_path+'testing-set.csv',header=None)
    train = pd.read_csv(file_path+'training-set.csv',header=None)
    test.columns = cols
    train.columns = cols
    train = train.set_index('FileID')
    test = test.set_index('FileID')
    train_indices = train.index
    test_indices = test.index
    train = pd.concat([df.ix[train_indices],train],axis=1)
    y = train.pop('y')
    test = df.ix[test_indices]
    return train, y, test

get_list_FileID = lambda x:' '.join(list(x.FileID))
############ model ############
