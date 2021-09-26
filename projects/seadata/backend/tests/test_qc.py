from restapi.tests import API_URI, FlaskClient
from tests.custom import SeadataTests


class TestApp(SeadataTests):
    def test_01(self, client: FlaskClient) -> None:

        # Resourcs are disabled by default because RESOURCES_PROJECT is empty
        r = client.get(f"{API_URI}/ingestion/my_batch_id/qc/my_qc_name")
        assert r.status_code == 404

        r = client.put(f"{API_URI}/ingestion/my_batch_id/qc/my_qc_name")
        assert r.status_code == 404

        r = client.delete(f"{API_URI}/ingestion/my_batch_id/qc/my_qc_name")
        assert r.status_code == 404

        r = client.post(f"{API_URI}/ingestion/my_batch_id/qc/my_qc_name")
        assert r.status_code == 404

        # This should be in case of enabled Resources:

        # GET /ingestion/<batch_id>/qc/<qc_name>
        # PUT /ingestion/<batch_id>/qc/<qc_name>
        # DELETE /ingestion/<batch_id>/qc/<qc_name>
        """
        r = client.get(f"{API_URI}/ingestion/my_batch_id/qc/my_qc_name")
        assert r.status_code == 401

        r = client.put(f"{API_URI}/ingestion/my_batch_id/qc/my_qc_name")
        assert r.status_code == 401

        r = client.delete(f"{API_URI}/ingestion/my_batch_id/qc/my_qc_name")
        assert r.status_code == 401

        r = client.post(f"{API_URI}/ingestion/my_batch_id/qc/my_qc_name")
        assert r.status_code == 405

        r = client.patch(f"{API_URI}/ingestion/my_batch_id/qc/my_qc_name")
        assert r.status_code == 401

        headers = self.login(client)

        r = client.put(
            f"{API_URI}/ingestion/my_batch_id/qc/my_qc_name", headers=headers
        )
        assert r.status_code == 400
        response = self.get_content(r)

        assert isinstance(response, dict)
        self.check_endpoints_input_schema(response)
        """