from flask import request, jsonify


def register_db_api(app, service_manager):
    """Register Mongo-backed service APIs on the given Flask app.

    Endpoints:
      - GET /api/db/services?name=&namespace=&tag=&created_by=&limit=&offset=&sort=
      - GET /api/db/services/<service_name>
      - GET /api/db/<collection>?service_name=&name=&limit=&offset=&sort=
    """

    @app.route('/api/db/services', methods=['GET'])
    def db_list_services():
        try:
            all_services = service_manager.get_services() or []

            name_q = (request.args.get('name') or '').strip().lower()
            ns_q = (request.args.get('namespace') or '').strip()
            tag_q = (request.args.get('tag') or '').strip().lower()
            created_by_q = (request.args.get('created_by') or '').strip().lower()
            sort_q = (request.args.get('sort') or 'name').strip()
            try:
                limit_q = int(request.args.get('limit', '50'))
                offset_q = int(request.args.get('offset', '0'))
                limit_q = max(1, min(limit_q, 500))
                offset_q = max(0, offset_q)
            except Exception:
                limit_q, offset_q = 50, 0

            def to_lower(x):
                return str(x).lower() if x is not None else ''

            filtered = []
            for s in all_services:
                name_val = s.get('name') or s.get('service_name') or ''
                ns_val = s.get('namespace') or ''
                tags_val = s.get('tags') or s.get('metadata', {}).get('tags') or []
                created_by_val = (s.get('created_by') or s.get('metadata', {}).get('created_by') or '')

                if name_q and name_q not in to_lower(name_val):
                    continue
                if ns_q and ns_q != ns_val:
                    continue
                if tag_q:
                    tag_list = [to_lower(t) for t in (tags_val or [])]
                    if tag_q not in tag_list:
                        continue
                if created_by_q and created_by_q != to_lower(created_by_val):
                    continue

                filtered.append(s)

            reverse = False
            key = 'name'
            if sort_q.startswith('-'):
                reverse = True
                sort_q = sort_q[1:]
            if sort_q in ['name', 'created_at']:
                key = sort_q
            filtered.sort(key=lambda x: (x.get(key) or ''), reverse=reverse)

            total = len(filtered)
            items = filtered[offset_q: offset_q + limit_q]

            return jsonify({'total': total, 'limit': limit_q, 'offset': offset_q, 'items': items})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/db/services/<service_name>', methods=['GET'])
    def db_get_service(service_name):
        try:
            all_services = service_manager.get_services() or []
            svc = next((s for s in all_services if (s.get('name') or s.get('service_name')) == service_name), None)
            if not svc:
                return jsonify({'error': 'Not found'}), 404
            return jsonify({'service': svc})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/db/<collection>', methods=['GET'])
    def db_list_collection(collection):
        try:
            valid = {
                'services', 'deployments', 'k8s_services', 'configmaps', 'hpas',
                'ingresses', 'namespaces', 'secrets', 'argocd_applications', 'manifest_versions'
            }
            if collection not in valid:
                return jsonify({'error': f'Unsupported collection: {collection}'}), 400

            getter_name = f'get_{collection}'
            if not hasattr(service_manager, getter_name):
                return jsonify({'error': 'Not implemented'}), 501

            getter = getattr(service_manager, getter_name)
            docs = getter() or []

            service_name_q = (request.args.get('service_name') or '').strip()
            name_q = (request.args.get('name') or '').strip()
            sort_q = (request.args.get('sort') or '').strip()
            try:
                limit_q = int(request.args.get('limit', '50'))
                offset_q = int(request.args.get('offset', '0'))
                limit_q = max(1, min(limit_q, 500))
                offset_q = max(0, offset_q)
            except Exception:
                limit_q, offset_q = 50, 0

            def match(doc):
                if service_name_q and (doc.get('service_name') or doc.get('name')) != service_name_q:
                    return False
                if name_q and (doc.get('name') or '') != name_q:
                    return False
                return True

            filtered = [d for d in docs if match(d)]

            reverse = False
            key = None
            if sort_q:
                if sort_q.startswith('-'):
                    reverse = True
                    sort_q = sort_q[1:]
                key = sort_q
            if key:
                filtered.sort(key=lambda x: (x.get(key) or ''), reverse=reverse)

            total = len(filtered)
            items = filtered[offset_q: offset_q + limit_q]
            return jsonify({'total': total, 'limit': limit_q, 'offset': offset_q, 'items': items})
        except Exception as e:
            return jsonify({'error': str(e)}), 500


