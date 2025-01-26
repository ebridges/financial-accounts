import json

from financial_accounts.business.base_service import BaseService
from financial_accounts.db.models import Base


class ManagementService(BaseService):

    def reset_database(self):
        connection = BaseService.shared_session.connection()
        Base.metadata.drop_all(connection)
        Base.metadata.create_all(connection)

    def export_account_hierarchy_as_json(self):
        """
        Returns a JSON string representing the hierarchical structure
        of the 'account' table (arbitrary parent->child depth).
        """

        # Step 1: Run a recursive CTE query to get each account, its parent, and depth
        rows = self.data_access.list_account_hierarchy()

        # Step 2: Build a dictionary for quick lookup, with a placeholder for 'children'
        # rows is a list of Row objects; each row has (id, parent_account_id, code, name, depth)
        nodes_by_id = {}
        for row in rows:
            node = {
                "id": row.id,
                "parent_account_id": row.parent_account_id,
                "code": row.code,
                "name": row.name,
                "depth": row.depth,
                "children": [],
            }
            nodes_by_id[row.id] = node

        # Step 3: Link children to parents
        #         We'll keep track of all "root" nodes (those with no parent) in a list
        root_nodes = []
        for row in rows:
            node = nodes_by_id[row.id]
            if node["parent_account_id"] is None:
                # No parent => It's a root node
                root_nodes.append(node)
            else:
                # Add this node to its parent's "children" list
                parent = nodes_by_id[node["parent_account_id"]]
                parent["children"].append(node)

        # Step 4: Convert the list of root nodes (which contain nested children) to JSON
        return json.dumps(root_nodes, indent=2)
