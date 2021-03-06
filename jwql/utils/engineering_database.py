#! /usr/bin/env python
"""Module to interface the JWST DMS Engineering Database.

This module provides ``jwql`` with classes and functions to interface
and query the JWST DMS Engineering Database.

Authors
-------

    - Johannes Sahlmann

Use
---

    This module can be imported and used with

    ::

        from jwql.utils.engineering_database import query_single_mnemonic
        query_single_mnemonic(mnemonic_identifier, start_time, end_time)

    Required arguments:

    ``mnemonic_identifier`` - String representation of a mnemonic name.
    ``start_time`` - astropy.time.Time instance
    ``end_time`` - astropy.time.Time instance

Notes
-----
    This module is built on top of ``astroquery.mast`` and uses
    JWST-specific MAST services.
    The user has to provide a valid MAST authentication token.

References
----------
    The MAST JWST EDB web portal is located at
    ``https://mast.stsci.edu/portal/Mashup/Clients/JwstEdb/JwstEdb.html``
"""

import astropy
from astropy.table import Table
from astropy.time import Time
from astroquery.mast import Mast
from bokeh.embed import components
from bokeh.plotting import figure

from .utils import get_config

# should use oauth.register_oauth()?
settings = get_config()
mast_token = settings['mast_token']

Mast.login(token=mast_token)

# could eventually be moved to constants.py
mast_edb_timeseries_service = 'Mast.JwstEdb.GetTimeseries.All'
mast_edb_dictionary_service = 'Mast.JwstEdb.Dictionary'
mast_edb_mnemonic_service = 'Mast.JwstEdb.Mnemonics'


class EdbMnemonic:
    """Class to hold and manipulate results of DMS EngDB queries."""

    def __init__(self, mnemonic_identifier, start_time, end_time, data, meta, info):
        """Populate attributes.

        Parameters
        ----------
        mnemonic_identifier : str
            Telemetry mnemonic identifier
        start_time : astropy.time.Time instance
            Start time
        end_time : astropy.time.Time instance
            End time
        data : astropy.table.Table
            Table representation of the returned data.
        meta : dict
            Additional information returned by the query
        info : dict
            Auxiliary information on the mnemonic (description,
            category, unit)
        """

        self.mnemonic_identifier = mnemonic_identifier
        self.start_time = start_time
        self.end_time = end_time
        self.data = data
        self.meta = meta
        self.info = info

    def __str__(self):
        """Return string describing the instance."""
        return 'EdbMnemonic {} with {} records between {} and {}'.format(
            self.mnemonic_identifier, len(self.data), self.start_time.isot,
            self.end_time.isot)

    def interpolate(self, times, **kwargs):
        """Interpolate value at specified times."""
        raise NotImplementedError

    def bokeh_plot(self):
        """Basic bokeh plot showing value as a function of time.

        Returns
        -------
        [div, script] : list
            List containing the div and js representations of figure.

        """

        abscissa = Time(self.data['MJD'], format='mjd').datetime
        ordinate = self.data['euvalue']

        p1 = figure(tools='pan,box_zoom,reset,wheel_zoom,save', x_axis_type='datetime',
                    title=self.mnemonic_identifier, x_axis_label='Time',
                    y_axis_label='Value ({})'.format(self.info['unit']))
        p1.line(abscissa, ordinate, line_width=1, line_color='blue', line_dash='dashed')
        p1.circle(abscissa, ordinate, color='blue')

        script, div = components(p1)

        return [div, script]


def is_valid_mnemonic(mnemonic_identifier):
    """Determine if the given string is a valid EDB mnemonic.

    Parameters
    ----------
    mnemonic_identifier : str
        The mnemonic_identifier string to be examined.

    Returns
    -------
    bool
        Is mnemonic_identifier a valid EDB mnemonic?
    """
    inventory = mnemonic_inventory()[0]
    if mnemonic_identifier in inventory['tlmMnemonic']:
        return True
    else:
        return False


def mnemonic_inventory():
    """Return all mnemonics in the DMS engineering database.

    Returns
    -------
    data : astropy.table.Table
        Table representation of the mnemonic inventory.
    meta : dict
        Additional information returned by the query.
    """

    out = Mast.service_request_async(mast_edb_mnemonic_service, {})
    data, meta = process_mast_service_request_result(out)
    return data, meta


def process_mast_service_request_result(result, data_as_table=True):
    """Parse the result of a MAST EDB query.

    Parameters
    ----------
    result : list of requests.models.Response instances
        The object returned by a call to ``Mast.service_request_async``
    data_as_table : bool
        If True, return data as astropy table, else return as json

    Returns
    -------
    data : astropy.table.Table
        Table representation of the returned data.
    meta : dict
        Additional information returned by the query
    """

    json_data = result[0].json()
    if json_data['status'] != 'COMPLETE':
        print(json_data['status'])
        raise RuntimeError('mnemonic query did not complete.')

    try:
        # timestamp-value pairs in the form of an astropy table
        if data_as_table:
            data = Table(json_data['data'])
        else:
            data = json_data['data'][0]
    except KeyError:
        raise RuntimeError('Query did not return any data.')

    # collect meta data
    meta = {}
    for key in json_data.keys():
        if key.lower() != 'data':
            meta[key] = json_data[key]

    return data, meta


def query_mnemonic_info(mnemonic_identifier):
    """Query the EDB to return the mnemonic description.

    Parameters
    ----------
    mnemonic_identifier : str
        Telemetry mnemonic identifier, e.g. ``SA_ZFGOUTFOV``

    Returns
    -------
    info : dict
        Object that contains the returned data
    """

    parameters = {"mnemonic": "{}".format(mnemonic_identifier)}
    result = Mast.service_request_async(mast_edb_dictionary_service, parameters)
    info = process_mast_service_request_result(result, data_as_table=False)[0]
    return info


def query_single_mnemonic(mnemonic_identifier, start_time, end_time):
    """Query DMS EDB to get the mnemonic readings in a time interval.

    Parameters
    ----------
    mnemonic_identifier : str
        Telemetry mnemonic identifier, e.g. 'SA_ZFGOUTFOV'
    start_time : astropy.time.Time instance
        Start time
    end_time : astropy.time.Time instance
        End time

    Returns
    -------
    mnemonic : instance of EdbMnemonic
        Object that contains the returned data
    """

    if not isinstance(start_time, astropy.time.core.Time):
        raise RuntimeError('Please specify a valid start time (instance of astropy.time.core.Time)')

    if not isinstance(end_time, astropy.time.core.Time):
        raise RuntimeError('Please specify a valid end time (instance of astropy.time.core.Time)')

    if not isinstance(mnemonic_identifier, str):
        raise RuntimeError('Please provide mnemonic_identifier of type string')

    parameters = {'mnemonic': mnemonic_identifier, 'start': start_time.iso, 'end': end_time.iso}
    result = Mast.service_request_async(mast_edb_timeseries_service, parameters)
    data, meta = process_mast_service_request_result(result)

    # get auxiliary information (description, subsystem, ...)
    info = query_mnemonic_info(mnemonic_identifier)

    # create and return instance
    mnemonic = EdbMnemonic(mnemonic_identifier, start_time, end_time, data, meta, info)
    return mnemonic
