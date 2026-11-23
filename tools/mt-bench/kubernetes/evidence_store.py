"""Private S3-API evidence store for cluster-resident campaigns (DigitalOcean Spaces live, MinIO on kind).

Standard library only (AWS Signature Version 4), so the controller image needs no SDK. Credentials and the endpoint
come from the environment, never from a file in Git:

  NS_EVIDENCE_ENDPOINT    https://sfo3.digitaloceanspaces.com  (MinIO: http://minio.bench-control.svc:9000)
  NS_EVIDENCE_BUCKET      the campaign's bucket
  NS_EVIDENCE_ACCESS_KEY / NS_EVIDENCE_SECRET_KEY
  NS_EVIDENCE_REGION      signing region (Spaces: the endpoint's region, e.g. sfo3; MinIO: us-east-1)
  NS_EVIDENCE_ADDRESSING  virtual (Spaces, documented) | path (MinIO)

Objects are written with `x-amz-acl: private`. Only the calls a campaign needs exist: put, get, list, delete, and the
bucket create/delete/head that `campaign.py` uses for MinIO and for `close`.
"""
import datetime as dt
import hashlib
import hmac
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

EMPTY = hashlib.sha256(b'').hexdigest()
NS = '{http://s3.amazonaws.com/doc/2006-03-01/}'


class StoreError(RuntimeError):
    def __init__(self, status, code, detail=''):
        super().__init__('EVIDENCE_STORE_%s' % (code or status))
        self.status, self.code, self.detail = status, code, detail


def _sign(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _quote(value, safe='/'):
    return urllib.parse.quote(value, safe=safe + '-_.~')


class Store:
    def __init__(self, endpoint, bucket, access_key, secret_key, region='us-east-1', addressing='path', timeout=60,
                 opener=None):
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ValueError('EVIDENCE_STORE_ENDPOINT')
        if addressing not in ('path', 'virtual'):
            raise ValueError('EVIDENCE_STORE_ADDRESSING')
        if not bucket or not access_key or not secret_key:
            raise ValueError('EVIDENCE_STORE_CREDENTIALS')
        self.scheme, self.host, self.bucket = parsed.scheme, parsed.netloc, bucket
        self.access_key, self.secret_key, self.region = access_key, secret_key, region
        self.addressing, self.timeout = addressing, timeout
        self.opener = opener or urllib.request.urlopen

    @classmethod
    def from_env(cls, env=None, bucket=None):
        env = os.environ if env is None else env
        return cls(env.get('NS_EVIDENCE_ENDPOINT', ''), bucket or env.get('NS_EVIDENCE_BUCKET', ''),
                   env.get('NS_EVIDENCE_ACCESS_KEY', ''), env.get('NS_EVIDENCE_SECRET_KEY', ''),
                   env.get('NS_EVIDENCE_REGION', 'us-east-1'), env.get('NS_EVIDENCE_ADDRESSING', 'path'))

    def describe(self):
        """Safe to log: no credentials."""
        return {'endpoint': '%s://%s' % (self.scheme, self.host), 'bucket': self.bucket, 'addressing': self.addressing}

    def _target(self, key):
        if self.addressing == 'virtual':
            return self.bucket + '.' + self.host, '/' + _quote(key) if key else '/'
        return self.host, '/' + self.bucket + ('/' + _quote(key) if key else '')

    def request(self, method, key='', query=None, body=b'', headers=None, bucket_level=False):
        host, path = self._target('' if bucket_level else key)
        query = sorted((query or {}).items())
        canonical_query = '&'.join('%s=%s' % (_quote(k, ''), _quote(str(v), '')) for k, v in query)
        now = dt.datetime.now(dt.timezone.utc)
        stamp, day = now.strftime('%Y%m%dT%H%M%SZ'), now.strftime('%Y%m%d')
        payload = hashlib.sha256(body).hexdigest() if body else EMPTY
        hdrs = {'host': host, 'x-amz-content-sha256': payload, 'x-amz-date': stamp}
        hdrs.update({k.lower(): v for k, v in (headers or {}).items()})
        signed = ';'.join(sorted(hdrs))
        canonical = '\n'.join([method, path, canonical_query,
                               ''.join('%s:%s\n' % (k, str(hdrs[k]).strip()) for k in sorted(hdrs)), signed, payload])
        scope = '%s/%s/s3/aws4_request' % (day, self.region)
        to_sign = '\n'.join(['AWS4-HMAC-SHA256', stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])
        key_ = _sign(_sign(_sign(_sign(('AWS4' + self.secret_key).encode(), day), self.region), 's3'), 'aws4_request')
        signature = hmac.new(key_, to_sign.encode(), hashlib.sha256).hexdigest()
        hdrs['authorization'] = 'AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s' % (
            self.access_key, scope, signed, signature)
        url = '%s://%s%s%s' % (self.scheme, host, path, '?' + canonical_query if canonical_query else '')
        req = urllib.request.Request(url, data=body if method in ('PUT', 'POST') else None, method=method,
                                     headers={k: v for k, v in hdrs.items() if k != 'host'})
        try:
            with self.opener(req, timeout=self.timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            raw = error.read()
            code = ''
            try:
                code = ET.fromstring(raw).findtext('Code') or ''
            except ET.ParseError:
                pass
            raise StoreError(error.code, code, raw[:300].decode(errors='replace')) from None

    # objects
    def put(self, key, body, content_type='application/octet-stream'):
        self.request('PUT', key, body=body, headers={'content-type': content_type, 'x-amz-acl': 'private'})

    def get(self, key):
        return self.request('GET', key)[1]

    def delete(self, key):
        self.request('DELETE', key)

    def list(self, prefix=''):
        """[{key, bytes, etag}] for every object under the prefix (ListObjectsV2, all pages)."""
        out, token = [], None
        while True:
            query = {'list-type': '2', 'prefix': prefix}
            if token:
                query['continuation-token'] = token
            _, raw = self.request('GET', query=query, bucket_level=True)
            root = ET.fromstring(raw)
            for item in root.iter(NS + 'Contents'):
                out.append({'key': item.findtext(NS + 'Key'), 'bytes': int(item.findtext(NS + 'Size') or 0),
                            'etag': (item.findtext(NS + 'ETag') or '').strip('"')})
            if root.findtext(NS + 'IsTruncated') != 'true':
                return out
            token = root.findtext(NS + 'NextContinuationToken')

    # bucket
    def bucket_exists(self):
        try:
            self.request('HEAD', bucket_level=True)
            return True
        except StoreError as error:
            if error.status == 404:
                return False
            raise

    def create_bucket(self):
        self.request('PUT', bucket_level=True, headers={'x-amz-acl': 'private'})

    def delete_bucket(self):
        """The bucket must be empty (Spaces API, documented); a non-empty bucket raises BucketNotEmpty."""
        self.request('DELETE', bucket_level=True)
