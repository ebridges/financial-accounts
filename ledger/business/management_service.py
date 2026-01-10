import json

from sqlalchemy import text

from ledger.business.base_service import BaseService
from ledger.db.models import Base


class ManagementService(BaseService):

    def reset_database(self):
        connection = self.session.connection()
        Base.metadata.drop_all(connection)
        Base.metadata.create_all(connection)

    def export_account_hierarchy_as_json(self):
        """
        Returns a JSON string representing the hierarchical structure
        of the 'account' table (arbitrary parent->child depth).
        """

        # Step 1: Run a recursive CTE query to get each account, its parent, and depth
        rows = self.list_account_hierarchy()

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

    def list_account_hierarchy(self):
        # Step 1: Run a recursive CTE query to get each account, its parent, and depth
        recursive_cte_query = text(
            """
            WITH RECURSIVE account_hierarchy AS (
                -- Anchor: all root accounts (no parent)
                SELECT
                    id,
                    parent_account_id,
                    code,
                    name,
                    0 AS depth
                FROM account
                WHERE parent_account_id IS NULL

                UNION ALL

                -- Recursive: join children to their parent in this CTE
                SELECT
                    c.id,
                    c.parent_account_id,
                    c.code,
                    c.name,
                    ah.depth + 1 AS depth
                FROM account c
                JOIN account_hierarchy ah
                ON c.parent_account_id = ah.id
            )
            SELECT
                id,
                parent_account_id,
                code,
                name,
                depth
            FROM account_hierarchy
            -- You can choose your own ORDER BY column(s)
            ORDER BY code
        """
        )

        result = self.session.execute(recursive_cte_query)
        return result.fetchall()
