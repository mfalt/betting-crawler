#!/usr/bin/env python3

import psycopg2, psycopg2.extras
import sys, time

from decimal import Decimal
from teams import teams
from time import gmtime, strftime

DEBUG = False
DECIMALS = 2
PRECISION = DECIMALS + 2


class match_database:

    def create_database(self):
        db = psycopg2.connect(host='ec2-54-83-198-111.compute-1.amazonaws.com', user='pjormmuewnnkwm', password='tf5q17_nrEOswfolbd3PS6wmNF', port=5432)
        db.cursor().execute('CREATE DATABASE %s;' % self.database_name)
        db.commit()
        db.close()


    def connect(self):
        self.connection = psycopg2.connect(host='ec2-54-83-198-111.compute-1.amazonaws.com', user='pjormmuewnnkwm', password='tf5q17_nrEOswfolbd3PS6wmNF', dbname='da3j6ejvc5arr0', port=5432)


    def create_table(self):
        table_exists_statement = "SELECT EXISTS(SELECT * FROM information_schema.tables WHERE table_name='%s');" % self.matches_table
        self.execute(table_exists_statement)

        if self.cursor.fetchone()[0]:
            return

        statement = "CREATE TABLE %s (competition VARCHAR(100), home VARCHAR(100), " % self.matches_table
        statement += "away VARCHAR(100), date DATE, time VARCHAR(5), "
        statement += '"%s" DECIMAL(%d,%d), ' % (self.odds_cols[0], PRECISION, DECIMALS)
        statement += '"%s" DECIMAL(%d,%d), ' % (self.odds_cols[1], PRECISION, DECIMALS)
        statement += '"%s" DECIMAL(%d,%d), ' % (self.odds_cols[2], PRECISION, DECIMALS)
        statement += "%s TIMESTAMP, site VARCHAR(100));" % self.timestamp_col

        self.execute(statement)


    def __init__(self):

        self.log = open('.database_actions.log', 'a')
        
        self.database_name  = "odds_data"
        self.matches_table  = "matches"
        
        self.odds_cols      = ['1', 'X', '2']
        self.timestamp_col  = "timestamp"
        
        self.teams          = teams()

        try:
            self.connect()

        except psycopg2.OperationalError:
            self.create_database()
            self.connect()

        self.cursor = self.connection.cursor(cursor_factory = psycopg2.extras.DictCursor)
        self.create_table()


    def execute(self, statement, commit=True):
        self.log.write("%s\n\n" % statement)
        self.cursor.execute(statement)

        if commit:
            self.connection.commit()


    def truncate_string(self, data):
        return data[:25] + (data[25:] and '..')


    def insert_match(self, comp, home_team, away_team, sql_date, clock_time, site, odds, timestamp):

        insert_query = "INSERT INTO matches (competition, home, away, date, time, site, "
        
        insert_query += '"%s", ' % self.odds_cols[0]
        insert_query += '"%s", ' % self.odds_cols[1]
        insert_query += '"%s", ' % self.odds_cols[2]
        insert_query += '%s) ' % self.timestamp_col

        insert_query += "VALUES('%s', '%s', '%s', '%s', '%s', '%s', " % (comp, home_team, away_team, sql_date, clock_time, site)
        insert_query += "'%s', " % odds['1']
        insert_query += "'%s', " % odds['X']
        insert_query += "'%s', " % odds['2']
        insert_query += "'%s');" % timestamp

        self.execute(insert_query)
        print('ADDED "%s - %s (%s)"' % (home_team, away_team, sql_date))


    def update_time(self, home_team, away_team, sql_date, clock_time, site, timestamp):
        statement = "UPDATE %s SET " % self.matches_table
        statement += "time='%s', " % clock_time
        statement += "%s='%s'" % (self.timestamp_col, timestamp)

        statement += " WHERE home = '" + home_team
        statement += "' AND away ='" + away_team
        statement += "' AND site ='" + site
        statement += "' AND date ='" + sql_date + "';"

        self.execute(statement)

    def update_odds(self, comp, home_team, away_team, sql_date, site, new_odds, old_odds, timestamp):
       
        changed_odds = {}
        changed_odds_list = []
        for col in self.odds_cols:
            if Decimal(str(new_odds[col])) == old_odds[col]:
                continue
            changed_odds[col] = Decimal(str(new_odds[col])) - old_odds[col]
            changed_odds_list.append((col, changed_odds[col]))

        if not changed_odds:
            return False

        pairs = []
        sign_string = "%+." + str(DECIMALS) + "f"
        format_string = "%s: " + "%s -> %s (%s)" % (sign_string, sign_string, sign_string)
        
        print('\nUPDATING "%s - %s, %s"' % (home_team, away_team, sql_date))
        for (col, odds_change) in changed_odds_list:
            print(format_string % (col, old_odds[col],
                Decimal(new_odds[col]), odds_change))
            pairs.append('"%s"=\'%s\'' % (col, new_odds[col]))

        statement = "UPDATE %s SET " % self.matches_table
        statement += ", ".join(pairs)
        statement += " WHERE home = '" + home_team
        statement += "' AND away ='" + away_team
        statement += "' AND site ='" + site
        statement += "' AND date ='" + sql_date + "';"

        print(statement)
        #import ipdb; ipdb.set_trace()
        self.execute(statement)

        return True

    def process_match(self, comp, home_team, away_team, sql_date, clock_time, site, odds):

        timestamp = time.strftime('%Y-%m-%d %H:%M:%S %z')

        home_team = self.teams.get_synonym(home_team)
        away_team = self.teams.get_synonym(away_team)
        
        sql_query = 'SELECT "1", "X", "2" FROM matches WHERE '
        sql_query += "home = '" + home_team
        sql_query += "' AND away = '" + away_team
        sql_query += "' AND site = '" + site
        sql_query += "' AND date = '" + sql_date + "';"

        self.execute(sql_query, commit=False)
        
        match = self.cursor.fetchone()
        if match is None:
            self.insert_match(comp, home_team, away_team, sql_date, clock_time, site, odds, timestamp)
            return True

        self.update_time(home_team, away_team, sql_date, clock_time, site, timestamp)

        old_odds = {col: match[col] for col in self.odds_cols}
        return self.update_odds(comp, home_team, away_team, sql_date, site, odds, old_odds, timestamp)

    def find_arbitrages(self):

        find_duplicates_statement = "SELECT min(competition) as competition, home, away, date FROM matches GROUP BY "
        find_duplicates_statement += "home, away, date HAVING COUNT(*) > 1;"
        self.execute(find_duplicates_statement, commit=False)

        found = 0
        for match in self.cursor.fetchall():

            statement = 'SELECT "1", "X", "2", site FROM matches WHERE '
            statement += "home = '" + match['home']
            statement += "' AND away = '" + match['away']
            statement += "' AND date = '" + str(match['date']) + "';"

            self.execute(statement)

            max_odds = {}

            for odds_row in self.cursor.fetchall():
                for col in self.odds_cols:

                    if col not in max_odds or odds_row[col] > max_odds[col]['odds']:
                        max_odds[col] = {'odds': odds_row[col], 'site': [odds_row['site']]}
                    elif odds_row[col] == max_odds[col]['odds']:
                        max_odds[col]['site'].append(odds_row['site'])

            arbitrage_sum = 0

            for col in self.odds_cols:
                arbitrage_sum += 1 / max_odds[col]['odds']

            if arbitrage_sum >= 1 and not DEBUG:
                continue

            found += 1
            print("%s: %s - %s, %s" % \
                    (match['competition'], match['home'], match['away'], str(match['date'])))

            for col in self.odds_cols:
                print(col + ": " + str(max_odds[col]['odds']) + \
                        " (" + ', '.join(max_odds[col]['site']) + ")")

            print("Arbitrage strength: {:.2f}%\n"
                    .format((1 - arbitrage_sum) * 100))

        if found == 0:
            print("No arbitrages found")


    def remove_old_matches(self):

        statement = 'DELETE FROM matches WHERE '
        statement += "%s < '%s'" % (self.timestamp_col, strftime("%Y-%m-%d", gmtime()))
        self.execute(statement)
