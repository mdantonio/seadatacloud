import json

from restapi.tests import API_URI, FlaskClient
from tests.custom import SeadataTests


class TestApp(SeadataTests):
    def test_01(self, client: FlaskClient) -> None:

        # POST /api/ingestion/my_batch_id/approve
        r = client.post(f"{API_URI}/ingestion/my_batch_id/approve")
        assert r.status_code == 401
        r = client.get(f"{API_URI}/ingestion/my_batch_id/approve")
        assert r.status_code == 405
        r = client.put(f"{API_URI}/ingestion/my_batch_id/approve")
        assert r.status_code == 405
        r = client.delete(f"{API_URI}/ingestion/my_batch_id/approve")
        assert r.status_code == 405
        r = client.patch(f"{API_URI}/ingestion/my_batch_id/approve")
        assert r.status_code == 405

        headers = self.login(client)

        r = client.post(
            f"{API_URI}/ingestion/my_batch_id/approve",
            headers=headers,
            json={}
        )
        assert r.status_code == 400
        response = self.get_content(r)

        assert isinstance(response, dict)
        self.check_endpoints_input_schema(response)

        data = self.get_input_data()
        r = client.post(
            f"{API_URI}/ingestion/my_batch_id/approve", headers=headers, json=data
        )
        assert r.status_code == 400
        assert self.get_seadata_response(r) == "pids parameter is empty list"

        data["parameters"] = json.dumps({"pids": []})
        r = client.post(
            f"{API_URI}/ingestion/my_batch_id/approve", headers=headers, json=data
        )
        assert r.status_code == 400
        assert self.get_seadata_response(r) == "pids parameter is empty list"

        data["parameters"] = json.dumps({"pids": ["wrong"]})

        r = client.post(
            f"{API_URI}/ingestion/my_batch_id/approve", headers=headers, json=data
        )
        assert r.status_code == 400
        assert (
            self.get_seadata_response(r)
            == "File list contains at least one wrong entry"
        )
