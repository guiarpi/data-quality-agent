# NYC 311 Service Requests — Data Dictionary

Source: [NYC Open Data — 311 Service Requests from 2010 to Present](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9)  
Asset ID: `erm2-nwe9`  
Column definitions transcribed from the dataset's official column metadata.

Variable names below match the **API/SoQL** CSV headers (snake_case). If you
download the CSV from the portal's Export button instead, the headers are
Title Case (`Unique Key`, `Created Date`) — the agent's
`case_insensitive_column_match` will not bridge that difference, so prefer the
API download command in README.md.

| Variable | Definition | Data Type |
| --- | --- | --- |
| unique_key | Unique identifier of a Service Request (SR) in the open data set | String |
| created_date | Date SR was created | Timestamp |
| closed_date | Date SR was closed by responding agency | Timestamp |
| agency | Acronym of responding City Government Agency | String |
| agency_name | Full Agency name of responding City Government Agency | String |
| complaint_type | First level of a hierarchy identifying the topic of the incident or condition | String |
| descriptor | Associated to the Complaint Type; provides further detail on the incident or condition | String |
| descriptor_2 | A third level of detail about the Complaint Type beyond the Descriptor | String |
| location_type | Describes the type of location used in the address information | String |
| incident_zip | Incident location zip code, provided by geo validation | String |
| incident_address | House number of incident address provided by submitter | String |
| street_name | Street name of incident address provided by the submitter | String |
| cross_street_1 | First cross street based on the geo validated incident location | String |
| cross_street_2 | Second cross street based on the geo validated incident location | String |
| intersection_street_1 | First intersecting street based on geo validated incident location | String |
| intersection_street_2 | Second intersecting street based on geo validated incident location | String |
| address_type | Type of incident location information available | String |
| city | City of the incident location provided by geovalidation | String |
| landmark | If the incident location is identified as a Landmark the name of the landmark displays here | String |
| facility_type | If available, describes the type of city facility associated to the SR | String |
| status | Status of SR submitted | String |
| due_date | Date when responding agency is expected to update the SR, based on Complaint Type and internal SLAs | Timestamp |
| resolution_description | Describes the last action taken on the SR by the responding agency | String |
| resolution_action_updated_date | Date when responding agency last updated the SR | Timestamp |
| community_board | Community board of the incident, provided by geovalidation | String |
| council_district | The City Council district where the service request is located | String |
| police_precinct | The NYPD precinct where the service request is located | String |
| bbl | Borough Block and Lot, provided by geovalidation. Parcel number identifying buildings and properties in NYC | String |
| borough | Borough provided by the submitter and confirmed by geovalidation | String |
| x_coordinate_state_plane | Geo validated X coordinate of the incident location | Number |
| y_coordinate_state_plane | Geo validated Y coordinate of the incident location | Number |
| open_data_channel_type | Indicates how the SR was submitted to 311: Phone, Online, Mobile, Other or Unknown | String |
| park_facility_name | If the incident location is a Parks Dept facility, the name of the facility | String |
| park_borough | The borough of incident if it is a Parks Dept facility | String |
| vehicle_type | If the incident is a taxi, describes the type of TLC vehicle | String |
| taxi_company_borough | If the incident is identified as a taxi, the borough of the taxi company | String |
| taxi_pick_up_location | If the incident is identified as a taxi, the taxi pick up location | String |
| bridge_highway_name | If the incident is identified as a Bridge/Highway, the name | String |
| bridge_highway_direction | If the incident is a Bridge/Highway, the direction where the issue took place | String |
| road_ramp | If the incident location was Bridge/Highway, differentiates Road vs Ramp | String |
| bridge_highway_segment | Additional information on the section of the Bridge/Highway where the incident took place | String |
| latitude | Geo based latitude of the incident location | Number |
| longitude | Geo based longitude of the incident location | Number |
| location | Combination of the geo based lat & long of the incident location | String |
