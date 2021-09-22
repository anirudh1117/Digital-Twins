# -*- coding: utf-8 -*-
"""
Created on Tue Aug 10 13:29:55 2021

@author: pkh35
"""
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, DateTime, Unicode, Date
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
from datetime import datetime
import requests
import geopandas as gpd
Base = declarative_base()

       
class User_log_info(Base):
    """Class to create tables"""
    __tablename__ = 'user_log_information'
    unique_id = Column(Integer, primary_key=True, autoincrement=True)
    source_list = Column(JSON())
    geometry = Column(Geometry('POLYGON'))
    accessed_date = Column(DateTime(timezone=True), default=func.now())

    
class Apilink(Base):
    __tablename__ = 'apilinks'
    source_name = Column(Unicode,primary_key=True, unique=True)
    source_apis = Column(Unicode)
    url = Column(Unicode)
    api_modified_date = Column(Date)
    region_name = Column(Unicode)
    access_date = Column(DateTime, default=datetime.now())
    query_dictionary= Column(JSON)
    geometry_col_name = Column(Unicode)
    geometry = Column(Geometry('MULTIPOLYGON'))
    
class dbsession():
    """Class to connect to postgreSQL"""
    def sessionCreate(self,table,engine):
        table.__table__.create(engine, checkfirst=True)
        
    def runQuery(self,engine,query):
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            session.add(query)
            session.commit()
        except: 
            session.rollback()
            
def table_exists(engine,name):
    ret = engine.dialect.has_table(engine, name)
    print('Table "{}" exists: {}'.format(name, ret))
    return ret

def region_geometry(key):
    #get the regional geometry data from Stats NZ 
    api = f"https://datafinder.stats.govt.nz/services;key={key}/wfs?service=WFS&version=2.0.0\
    &request=GetFeature&typeNames=layer-105133&&outputFormat=json"
    response = requests.get(api)
    response_data = gpd.read_file(response.text)
    response_data.columns= response_data.columns.str.lower()
    response_data  = response_data.to_crs(epsg=4326)
    nz_polygon = response_data.dissolve().explode()
    nz_polygon['REGC2021_V1_00_NAME'] = "New Zealand"
    response_data.loc[len(response_data.index)] = nz_polygon.iloc[0]
    return response_data
