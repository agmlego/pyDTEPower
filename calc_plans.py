# -*- coding: utf-8 -*-
# SPDX-License-Identifier: FAFOL
# pylint: disable=logging-fstring-interpolation


from csv import DictReader, DictWriter
from dataclasses import dataclass
from decimal import Decimal
import sys
from typing import Callable, Dict, List

import arrow


@dataclass
class RateCondition:
    key: str                                 # key to check
    condition: str                           # condition to check
    match: Callable[[Dict[str, str]], bool]  # function to match this rate

    def is_rate(self, row: Dict[str, str], debug: bool = False) -> bool:
        """
        Figure out if this rate applies to this row

        Args:
            row (Dict[str, str]): row of account data

        Returns:
            bool: whether this rate applies to this row
        """
        val = self.match(row)
        if debug and not val:
            print(f'No match for {self.key}: {self.condition}')
        return val


@dataclass
class PlanRate:
    name: str                           # rate name (e.g. First 17kWh)
    distribution: Decimal               # distribution charge per kWh in cents
    capacity: Decimal                   # capacity charge per kWh in cents
    non_capacity: Decimal               # non_capacity charge per kWh in cents
    conditions: List[RateCondition]     # conditions to match this rate

    def is_rate(self, row: Dict[str, str], debug: bool = False) -> bool:
        """
        Figure out if this rate applies to this row

        Args:
            row (Dict[str, str]): row of account data

        Returns:
            bool: whether this rate applies to this row
        """
        for condition in self.conditions:
            if not condition.is_rate(row, debug):
                return False
        return True

    def cost(self, row: Dict[str, str]) -> Decimal:
        """
        If this is a row for this rate, calculate the cost

        Args:
            row (Dict[str, str]): row of account data

        Returns:
            Decimal: $0.00 if not matching the rate,
                otherwise the cost in dollars for the row
        """
        if not self.is_rate(row):
            return Decimal('0.0')
        return Decimal(row['Hourly Total']) * (
            self.distribution +
            self.capacity +
            self.non_capacity
        ) / Decimal('100.0')


@dataclass
class PricePlan:
    name: str                   # plan name (e.g. D1)
    rates: List[PlanRate]       # one or more rates
    service_charge: Decimal     # per-month

    def match_rate(self, row: Dict[str, str]) -> PlanRate:
        """
        Determine which rate matches a row

        Args:
            row (Dict[str, str]): row of account data

        Returns:
            PlanRate: None if no rates match,
                otherwise the first PlanRate that matches
        """
        for rate in self.rates:
            if rate.is_rate(row):
                return rate
        print(f'{self.name}: Could not find rate for {row}!', file=sys.stderr)
        for rate in self.rates:
            rate.is_rate(row, debug=True)
        return None

    def cost(self, row: Dict[str, str]) -> Decimal:
        """
        Calculate the cost for this row

        Args:
            row (Dict[str, str]): row of account data

        Returns:
            Decimal: $0.00 if no matching rate,
                otherwise the cost in dollars for the row
        """
        rate = self.match_rate(row)
        if rate is None:
            return Decimal('0.0')
        return rate.cost(row)


if __name__ == '__main__':
    plans: List[PricePlan] = []
    # D1 residential pricing
    plans.append(PricePlan(
        name='D1',
        service_charge=Decimal('7.50'),
        rates=[
            PlanRate(
                name='First 17kWh',
                distribution=Decimal('6.611'),
                capacity=Decimal('4.500'),
                non_capacity=Decimal('4.176'),
                conditions=[
                    RateCondition(
                        key='Daily Cumulative',
                        condition='<=17',
                        match=lambda row: row['Daily Cumulative'] <= 17
                    ),
                ]
            ),
            PlanRate(
                name='After 17kWh',
                distribution=Decimal('6.611'),
                capacity=Decimal('6.484'),
                non_capacity=Decimal('4.176'),
                conditions=[
                    RateCondition(
                        key='Daily Cumulative',
                        condition='>17',
                        match=lambda row: row['Daily Cumulative'] > 17
                    ),
                ]
            ),
        ]
    ))

    # D1.2 Time of Day
    plans.append(PricePlan(
        name='D1.2',
        service_charge=Decimal('7.50'),
        rates=[
            PlanRate(
                name='Time-of-Day Summer Off-Peak',
                distribution=Decimal('6.611'),
                capacity=Decimal('1.160'),
                non_capacity=Decimal('4.261'),
                conditions=[
                    RateCondition(
                        key='Timestamp',
                        condition='06/01 <= day <= 10/31',
                        match=lambda row: row['Timestamp'].floor('day').is_between(
                            row['Timestamp'].clone().replace(month=6, day=1),
                            row['Timestamp'].clone().replace(month=10, day=31).ceil('day'), bounds='[]')
                    ),
                    RateCondition(
                        key='Timestamp',
                        condition='19:00:00 <= hour <= 10:59:59',
                        match=lambda row: row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=19),
                            row['Timestamp'].clone().replace(hour=23).ceil('hour'), bounds='[]') or
                        row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=0),
                            row['Timestamp'].clone().replace(hour=10).ceil('hour'), bounds='[]')
                    ),
                ]
            ),
            PlanRate(
                name='Time-of-Day Summer On-Peak',
                distribution=Decimal('6.611'),
                capacity=Decimal('11.841'),
                non_capacity=Decimal('4.261'),
                conditions=[
                    RateCondition(
                        key='Timestamp',
                        condition='06/01 <= day <= 10/31',
                        match=lambda row: row['Timestamp'].floor('day').is_between(
                            row['Timestamp'].clone().replace(month=6, day=1),
                            row['Timestamp'].clone().replace(month=10, day=31).ceil('day'), bounds='[]')
                    ),
                    RateCondition(
                        key='Timestamp',
                        condition='11:00:00 <= hour <= 18:59:59',
                        match=lambda row: row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=11),
                            row['Timestamp'].clone().replace(hour=18).ceil('hour'), bounds='[]')
                    ),
                ]
            ),
            PlanRate(
                name='Time-of-Day Winter Off-Peak',
                distribution=Decimal('6.611'),
                capacity=Decimal('0.948'),
                non_capacity=Decimal('4.261'),
                conditions=[
                    RateCondition(
                        key='Timestamp',
                        condition='11/01 <= day <= 5/31',
                        match=lambda row: row['Timestamp'].floor('day').is_between(
                            row['Timestamp'].clone().replace(month=11, day=1),
                            row['Timestamp'].clone().replace(month=5, day=31).shift(years=+1).ceil('day'), bounds='[]')
                    ),
                    RateCondition(
                        key='Timestamp',
                        condition='19:00:00 <= hour <= 10:59:59',
                        match=lambda row: row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=19),
                            row['Timestamp'].clone().replace(hour=23).ceil('hour'), bounds='[]') or
                        row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=0),
                            row['Timestamp'].clone().replace(hour=10).ceil('hour'), bounds='[]')
                    ),
                ]
            ),
            PlanRate(
                name='Time-of-Day Winter On-Peak',
                distribution=Decimal('6.611'),
                capacity=Decimal('9.341'),
                non_capacity=Decimal('4.261'),
                conditions=[
                    RateCondition(
                        key='Timestamp',
                        condition='11/01 <= day <= 5/31',
                        match=lambda row: row['Timestamp'].floor('day').is_between(
                            row['Timestamp'].clone().replace(month=11, day=1),
                            row['Timestamp'].clone().replace(month=5, day=31).shift(years=+1).ceil('day'), bounds='[]')
                    ),
                    RateCondition(
                        key='Timestamp',
                        condition='11:00:00 <= hour <= 18:59:59',
                        match=lambda row: row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=11),
                            row['Timestamp'].clone().replace(hour=18).ceil('hour'), bounds='[]')
                    ),
                ]
            ),
        ]
    ))

    # D1.9 Dynamic Time-of-Day
    plans.append(PricePlan(
        name='D1.9',
        service_charge=Decimal('7.50'),
        rates=[
            PlanRate(
                name='Dynamic Mid-Peak',
                distribution=Decimal('6.611'),
                capacity=Decimal('5.645'),
                non_capacity=Decimal('3.576'),
                conditions=[
                    RateCondition(
                        key='Timestamp',
                        condition='Monday <= day <= Friday',
                        match=lambda row: 0 <= row['Timestamp'].weekday() <= 4
                    ),
                    RateCondition(
                        key='Timestamp',
                        condition='19:00:00 <= hour <= 22:59:59 or 07:00:00 <= hour <= 14:59:59',
                        match=lambda row: row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=19),
                            row['Timestamp'].clone().replace(hour=22).ceil('hour'), bounds='[]') or
                        row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=7),
                            row['Timestamp'].clone().replace(hour=14).ceil('hour'), bounds='[]')
                    ),
                ]
            ),
            PlanRate(
                name='Dynamic On-Peak',
                distribution=Decimal('6.611'),
                capacity=Decimal('13.025'),
                non_capacity=Decimal('3.576'),
                conditions=[
                    RateCondition(
                        key='Timestamp',
                        condition='Monday <= day <= Friday',
                        match=lambda row: 0 <= row['Timestamp'].weekday() <= 4
                    ),
                    RateCondition(
                        key='Timestamp',
                        condition='15:00:00 <= hour <= 18:59:59',
                        match=lambda row: row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=15),
                            row['Timestamp'].clone().replace(hour=18).ceil('hour'), bounds='[]')
                    ),
                ]
            ),
            PlanRate(
                name='Dynamic Off-Peak Weekday',
                distribution=Decimal('6.611'),
                capacity=Decimal('1.218'),
                non_capacity=Decimal('3.576'),
                conditions=[
                    RateCondition(
                        key='Timestamp',
                        condition='Monday <= day <= Friday',
                        match=lambda row: 0 <= row['Timestamp'].weekday() <= 4
                    ),
                    RateCondition(
                        key='Timestamp',
                        condition='23:00:00 <= hour <= 06:59:59',
                        match=lambda row: row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=23),
                            row['Timestamp'].clone().replace(hour=23).ceil('hour'), bounds='[]') or
                        row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=0),
                            row['Timestamp'].clone().replace(hour=6).ceil('hour'), bounds='[]')
                    ),
                ]
            ),
            PlanRate(
                name='Dynamic Off-Peak Weekend',
                distribution=Decimal('6.611'),
                capacity=Decimal('1.218'),
                non_capacity=Decimal('3.576'),
                conditions=[
                    RateCondition(
                        key='Timestamp',
                        condition='Saturday <= day <= Sunday',
                        match=lambda row: 5 <= row['Timestamp'].weekday() <= 6
                    ),
                ]
            ),
        ]
    ))

    # D1.8 EV Dedicated Meter
    plans.append(PricePlan(
        name='D1.8',
        service_charge=Decimal('1.95'),
        rates=[
            PlanRate(
                name='EV On-Peak',
                distribution=Decimal('6.611'),
                capacity=Decimal('9.791'),
                non_capacity=Decimal('19.720'),
                conditions=[
                    RateCondition(
                        key='Timestamp',
                        condition='Monday <= day <= Friday',
                        match=lambda row: 0 <= row['Timestamp'].weekday() <= 4
                    ),
                    RateCondition(
                        key='Timestamp',
                        condition='09:00:00 <= hour <= 22:59:59',
                        match=lambda row: row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=9),
                            row['Timestamp'].clone().replace(hour=22).ceil('hour'), bounds='[]')
                    ),
                ]
            ),
            PlanRate(
                name='EV Off-Peak Weekday',
                distribution=Decimal('6.611'),
                capacity=Decimal('2.448'),
                non_capacity=Decimal('7.889'),
                conditions=[
                    RateCondition(
                        key='Timestamp',
                        condition='Monday <= day <= Friday',
                        match=lambda row: 0 <= row['Timestamp'].weekday() <= 4
                    ),
                    RateCondition(
                        key='Timestamp',
                        condition='23:00:00 <= hour <= 08:59:59',
                        match=lambda row: row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=23),
                            row['Timestamp'].clone().replace(hour=23).ceil('hour'), bounds='[]') or
                        row['Timestamp'].is_between(
                            row['Timestamp'].clone().replace(hour=0),
                            row['Timestamp'].clone().replace(hour=8).ceil('hour'), bounds='[]')
                    ),
                ]
            ),
            PlanRate(
                name='EV Off-Peak Weekend',
                distribution=Decimal('6.611'),
                capacity=Decimal('2.448'),
                non_capacity=Decimal('7.889'),
                conditions=[
                    RateCondition(
                        key='Timestamp',
                        condition='Saturday <= day <= Sunday',
                        match=lambda row: 5 <= row['Timestamp'].weekday() <= 6
                    ),
                ]
            ),
        ]
    ))

    data = {}
    for r in DictReader(open(sys.argv[1], newline='', encoding='utf-8')):
        acct = r['Account Number']
        meter = r['Meter Number']
        if acct not in data:
            data[acct] = {}
        if meter not in data[acct]:
            data[acct][meter] = []
        r['Timestamp'] = arrow.get(
            r['Day'] + ' ' + r['Hour of Day'],
            'MM/DD/YYYY h:mm A',
            tzinfo='America/Detroit')
        data[acct][meter].append(r)

    for acct in data:
        for meter in data[acct]:
            data[acct][meter] = sorted(
                data[acct][meter], key=lambda d: d['Timestamp'])

            ts = data[acct][meter][0]['Timestamp'].date()
            day_tally = Decimal('0.0')
            for idx in range(len(data[acct][meter])):
                if data[acct][meter][idx]['Timestamp'].date() > ts:
                    day_tally = Decimal('0.0')
                    ts = data[acct][meter][idx]['Timestamp'].date()
                data[acct][meter][idx]['Daily Cumulative'] = day_tally + \
                    Decimal(data[acct][meter][idx]['Hourly Total'])
                day_tally = data[acct][meter][idx]['Daily Cumulative']

                for plan in plans:
                    data[acct][meter][idx][plan.name +
                                           ' Rate'] = plan.match_rate(data[acct][meter][idx]).name
                    data[acct][meter][idx][plan.name +
                                           ' Cost'] = plan.cost(data[acct][meter][idx])

    with open(sys.argv[1], newline='', mode='w', encoding='utf-8') as csvfile:
        fieldnames = ["Account Number", "Meter Number", "Day", "Hour of Day", "Timestamp",
                      "Hourly Total", "Daily Cumulative", "Daily Total", "Unit of Measurement"]
        for plan in plans:
            fieldnames.append(plan.name + ' Rate')
            fieldnames.append(plan.name + ' Cost')

        writer = DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for acct in data:
            for meter in data[acct]:
                for r in data[acct][meter]:
                    writer.writerow(r)
