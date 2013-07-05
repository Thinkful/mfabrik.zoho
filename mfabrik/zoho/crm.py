"""

    Zoho CRM API bridge.

"""

__copyright__ = "2010 mFabrik Research Oy"
__author__ = "Mikko Ohtamaa <mikko@mfabrik.com>"
__license__ = "GPL"
__docformat__ = "Epytext"


try:
    from xml import etree
    from xml.etree.ElementTree import Element, tostring, fromstring
except ImportError:
    try:
        from lxml import etree
        from lxml.etree import Element, tostring, fromstring
    except ImportError:
        raise RuntimeError("XML library not available:  no etree, no lxml")
   
from core import Connection, ZohoException, decode_json

class CRM(Connection):
    """ CRM specific Zoho APIs mapped to Python """
    
    def get_service_name(self):
        """ Called by base class """
        return "ZohoCRM"
    
    def check_successful_xml(self, response):
        """ Make sure that we get "succefully" response.
        
        Throw exception of the response looks like something not liked.
        
        @raise: ZohoException if any error
        
        @return: Always True
        """

        # Example response
        # <response uri="/crm/private/xml/Leads/insertRecords"><result><message>Record(s) added successfully</message><recorddetail><FL val="Id">177376000000142007</FL><FL val="Created Time">2010-06-27 21:37:20</FL><FL val="Modified Time">2010-06-27 21:37:20</FL><FL val="Created By">Ohtamaa</FL><FL val="Modified By">Ohtamaa</FL></recorddetail></result></response>

        root = fromstring(response)

        # Check error response
        # <response uri="/crm/private/xml/Leads/insertRecords"><error><code>4401</code><message>Unable to populate data, please check if mandatory value is entered correctly.</message></error></response>
        for error in root.findall("error"):
            print "Got error"
            for message in error.findall("message"):
                raise ZohoException(message.text)
        
        return True
    
    def _xmlize_record(self, element_name, records):
        root = Element(element_name)

        # Row counter
        no = 1

        for lead in records:
            row = Element("row", no=str(no))
            root.append(row)

            assert type(lead) == dict, "Leads must be dictionaries inside a list, got:" + str(type(lead))
        
            for key, value in lead.items():
                # <FL val="Lead Source">Web Download</FL>
                # <FL val="First Name">contacto 1</FL>
                fl = Element("fl", val=key)
                fl.text = value
                row.append(fl)
                
            no += 1
            return root

    def _parse_json_response(self, response, record_name):
        # raw data looks like {'response': {'result': {'Leads': {'row': 
        # [{'FL': [{'content': '177376000000142085', 'val': 'LEADID'}, ...

        data =  decode_json(response)
        
        def parse_row(row):
            item = {}
            if type(row["FL"]) == list:
                for cell in row["FL"]:
                    item[cell["val"]] = cell["content"]
            elif type(row["FL"]) == dict:
                cell = row["FL"]
                item[cell["val"]] = cell["content"]
            else:
                raise ZohoException("Unknown structure to row '%s'" % row)
            return item
        # Sanify output data to more Python-like format
        
        if data["response"].has_key("nodata"):
            return []
        
        # are there times when there's 'response', no 'nodata'
        # that would require explicit checking for 'result' key??
        output = []
        rows = data["response"]["result"][record_name]["row"]
        if type(rows) == list:
            for row in rows:
                item = parse_row(row)
                output.append(item)
        elif type(rows) == dict:
            item = parse_row(rows)
            output.append(item)
        else:
            raise ZohoException("Unknown structure to rows '%s'" % rows)
        return output


    def _insert_records(self, record_name, method, records, extra_post_parameters={}):
        """ Insert new records (leads, contacts, etc) to Zoho CRM database.
        
        The contents of the record parameters can be defined in Zoho CRM itself.
        
        http://zohocrmapi.wiki.zoho.com/insertRecords-Method.html
        
        @param records: List of dictionaries. Dictionary content is directly mapped to 
            <FL> XML parameters as described in Zoho CRM API.
        
        @param extra_post_parameters: Parameters appended to the HTTP POST call. 
            Described in Zoho CRM API.
        
        @return: List of record ids which were created by insert recoreds
        """
        self.ensure_opened()
        root = self._xmlize_record(record_name, records)
        post = {
            'newFormat':    1,
            'duplicateCheck':   2
        }
        post.update(extra_post_parameters)
        response = self.do_xml_call(
            "https://crm.zoho.com/crm/private/xml/%s/%s" % (record_name, method), 
            post, root)
        self.check_successful_xml(response)
        return self.get_inserted_records(response)

    def insert_leads(self, leads, extra_post_parameters={}):
        return self._insert_records("Leads", "insertRecords", leads, extra_post_parameters)
    def insert_contacts(self, contacts, extra_post_parameters={}):
        return self._insert_records("Contacts", "insertRecords", contacts, extra_post_parameters)
    def insert_potentials(self, potentials, extra_post_parameters={}):
        return self._insert_records("Potentials", "insertRecords", potentials, extra_post_parameters)
    def insert_notes(self, notes, extra_post_parameters={}):
        return self._insert_records("Notes", "insertRecords", notes, extra_post_parameters)

    def update_contacts(self, contacts, extra_post_parameters={}):
        extra_post_parameters['version'] = 4
        return self._insert_records("Contacts", "updateRecords", contacts, extra_post_parameters)
    def update_leads(self, leads, extra_post_parameters={}):
        extra_post_parameters['version'] = 4
        return self._insert_records("Leads", "updateRecords", leads, extra_post_parameters)
    def update_potentials(self, potentials, extra_post_parameters={}):
        extra_post_parameters['version'] = 4
        return self._insert_records("Potentials", "updateRecords", potentials, extra_post_parameters)

    def get_inserted_records(self, response):
        """
        @return: List of record ids which were created by insert recoreds
        """
        root = fromstring(response)
        
        records = []
        for result in root.findall("result"):
            for record in result.findall("recorddetail"):
                record_detail = {}
                for fl in record.findall("FL"):
                    record_detail[fl.get("val")] = fl.text
                records.append(record_detail)
        return records
        
    def get_records(self, record_name, selectColumns, 
            from_index=None, to_index=None, parameters={}):
        """ 
        
        http://zohocrmapi.wiki.zoho.com/getRecords-Method.html
        
        @param selectColumns: String. What columns to query. For example query format,
            see API doc. Default is leads(First Name,Last Name,Company).
        
        @param parameters: Dictionary of filtering parameters which are part of HTTP POST to Zoho.
            For example parameters see Zoho CRM API docs.
        
        @return: Python list of dictionarizied leads. Each dictionary contains lead key-value pairs. LEADID column is always included.

        """
        
        self.ensure_opened()
        
        post_params = {
            "selectColumns" : selectColumns,
            "newFormat" : 2,
        }
        if from_index:
            post_params['fromIndex'] = from_index
        if to_index:
            post_params['toIndex'] = to_index

        post_params.update(parameters)

        response = self.do_call(
            "https://crm.zoho.com/crm/private/json/%s/getRecords" % (record_name), post_params)
        return self._parse_json_response(response, record_name)
    def get_record_by_id(self, record_id, record_name, selectColumns, parameters={}):
        """
        https://www.zoho.com/crm/help/api/getrecordbyid.html   

        Returns a Python list of length=1 of record dictionary, keys of which
        dependent on record type.

        """

        self.ensure_opened()

        post_params = {
            "id": record_id,
            "selectColumns" : selectColumns,
            "newFormat" : 2,
        }
        post_params.update(parameters)

        response = self.do_call(
            "https://crm.zoho.com/crm/private/json/%s/getRecordById" % (record_name), post_params)
        return self._parse_json_response(response, record_name)[0]

    def get_related_records(self, record_name, parent_module, contact_id, 
            from_index=0, to_index=200, parameters={}):
        
        self.ensure_opened()
        
        post_params = {
            "id" : contact_id,
            "newFormat" : 2,
            "parentModule" : parent_module,
            "fromIndex" : from_index,
            "toIndex" : to_index,
        }
        
        post_params.update(parameters)

        response = self.do_call(
            "https://crm.zoho.com/crm/private/json/%s/getRelatedRecords" % (record_name), post_params)
        return self._parse_json_response(response, record_name)

    def search_records(self, record_name, selectColumns, search_condition,
            from_index=None, to_index=None, parameters={}):
        self.ensure_opened()
        
        post_params = {
            "selectColumns" : selectColumns,
            "newFormat" : 2,
            "searchCondition": search_condition,
        }
        if from_index:
            post_params['fromIndex'] = from_index
        if to_index:
            post_params['toIndex'] = to_index

        post_params.update(parameters)

        response = self.do_call(
            "https://crm.zoho.com/crm/private/json/%s/getSearchRecords" % (record_name), post_params)
        return self._parse_json_response(response, record_name)

    def get_leads(self, 
            select_columns='leads(Email,First Name,Last Name,Lead Status,Email Opt Out,Signed up at,Created Time)', 
            **kwargs):
        return self.get_records("Leads", select_columns, **kwargs)
    def get_contacts(self, 
            select_columns='contacts(First Name,Last Name,Email,Contact Type,Email Opt Out,Signed up at,Created Time,Stripe Customer ID)', 
            **kwargs):
        return self.get_records("Contacts", select_columns, **kwargs)
    def get_potentials(self, 
            select_columns='potentials(Contact Name,Signed up at,Closing Date,Course,Stage,Lead Source,Exact lead source,Payer)', 
            **kwargs):
        return self.get_records("Potentials", select_columns, **kwargs)
    
    def get_contact_by_id(self, contact_id,
            select_columns='contacts(First Name,Last Name,Email,Contact Type,Email Opt Out,Signed up at,Created Time,Stripe Customer ID)',
            **kwargs):
        return self.get_record_by_id(contact_id, "Contacts", select_columns, **kwargs)
    def get_potential_by_id(self, potential_id,
            select_columns='potentials(Contact Name,Signed up at,Closing Date,Course,Stage,Lead Source,Exact lead source,Payer)', 
            **kwargs):
        return self.get_record_by_id(potential_id, "Potentials", select_columns, **kwargs)

        
    def get_contacts_for_potential(self, potential_id):
        return self.get_related_records('ContactRoles', 'Potentials', potential_id)
    def get_potentials_for_contact(self, contact_id):
        return self.get_related_records('Potentials', 'Contacts', contact_id)       
    def get_funnel_stages_for_potential(self, potential_id):
        return self.get_related_records('PotStageHistory', 'Potentials', potential_id)

    def search_leads(self, search_condition,
            select_columns='leads(Email,First Name,Last Name,Lead Status,Email Opt Out,Signed up at,Created Time)', 
            **kwargs):
        return self.search_records("Leads", select_columns, search_condition, **kwargs)
    def search_contacts(self, search_condition,
            select_columns='contacts(First Name,Last Name,Email,Thinkful login,Contact Type,Email Opt Out,Signed up at,Created Time,Stripe Customer ID)', 
            **kwargs):
        return self.search_records("Contacts", select_columns, search_condition, **kwargs)
    def search_potentials(self, search_condition,
            select_columns='potentials(Contact Name,Signed up at,Closing Date,Stage,Lead Source,Exact lead source)', 
            **kwargs):
        return self.search_records("Potentials", select_columns, search_condition, **kwargs)

    def delete_record(self, id, parameters={}):
        """ Delete one record from Zoho CRM.
                        
        @param id: Record id
        
        @param parameters: Extra HTTP post parameters        
        """
        
        self.ensure_opened()
    
        post_params = {}
        post_params["id"] = id
        post_params.update(parameters)
        
        response = self.do_call("https://crm.zoho.com/crm/private/xml/Leads/deleteRecords", post_params)
        
        self.check_successful_xml(response)

