"""Offline figure source, rights, raster, job and explicit revision regressions."""
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from literature_digest import figures
from literature_digest.agent_jobs import create_job, tool
from literature_digest.config import load_configs
from literature_digest.connector_delivery import begin_send, confirm_sent
from literature_digest.models import Paper
from literature_digest.render import _figures
from literature_digest.sources import safe_figure_url
import test_agent_jobs


def raster():
    output = io.BytesIO()
    Image.new('RGB', (2, 2), 'white').save(output, format='PNG')
    return output.getvalue()


def manifest():
    return {'paper_key': 'arxiv:2608.10277', 'id': 'Figure 5', 'caption': 'Figure 5: Original scientific comparison.',
            'explanation': '主要结果显示两种模型的比较。', 'source_url': 'https://arxiv.org/html/2608.10277v1#S3.F5',
            'url': 'https://arxiv.org/html/2608.10277v1/figure5.png', 'attribution': 'Original Authors',
            'license': 'CC BY 4.0', 'license_scope': 'article', 'license_url': 'https://arxiv.org/abs/2608.10277v1',
            'license_evidence': 'view license', 'rights_basis': 'Article license includes the original figure without a third-party credit.', 'original': True}


def fetcher(url, limit):
    if url.endswith('.png'):
        return raster(), 'image/png', url
    m = manifest()
    body = ('<html><p>' + m['caption'] + '</p><img src="' + m['url'] + '">' +
            '<a title="Rights to this article" href="https://creativecommons.org/licenses/by/4.0/">view license</a></html>').encode()
    return body, 'text/html', url


class OriginalFigures(unittest.TestCase):
    def setUp(self):
        self.paper = Paper(title='Original', source='arxiv', source_id='2608.10277', arxiv_id='2608.10277', url='https://arxiv.org/abs/2608.10277v1')

    def test_verified_original_freezes_bytes_and_caption_evidence(self):
        figure, asset = figures.register_figure(manifest(), self.paper, 'embed', fetcher)
        self.assertTrue(figure['embed_allowed'])
        self.assertTrue(figure['provenance']['license_evidence_verified'])
        self.assertEqual(base64.b64decode(asset['content_base64']), raster())
        self.assertEqual(figures.validate_inline_images([asset]), [asset])

    def test_link_only_for_unknown_rights_and_explicit_links(self):
        for mode, license_value in [('links', 'CC BY 4.0'), ('embed', 'arXiv nonexclusive'), ('embed', 'CC BY-NC-SA 4.0')]:
            with self.subTest(mode=mode, license=license_value), patch('literature_digest.figures.fetch_public') as fetch:
                figure, asset = figures.register_figure({**manifest(), 'license': license_value}, self.paper, mode)
                self.assertFalse(figure['embed_allowed']); self.assertIsNone(asset); fetch.assert_not_called()

    def test_noncommercial_license_needs_explicit_scope(self):
        def nc_fetch(url, maximum):
            raw, mime, final = fetcher(url, maximum)
            return raw.replace(b'licenses/by/4.0', b'licenses/by-nc-sa/4.0') if mime == 'text/html' else raw, mime, final
        figure, asset = figures.register_figure({**manifest(), 'license': 'CC BY-NC-SA 4.0'}, self.paper,
                                                'embed', nc_fetch, reuse_context='personal_noncommercial')
        self.assertTrue(figure['embed_allowed']); self.assertIsNotNone(asset)

    def test_reject_unrelated_page_identifier_in_bibliography_and_license_mismatch(self):
        for change in ({'source_url': 'https://example.org/unrelated'}, {'license_url': 'https://arxiv.org/abs/2601.11111'},
                       {'license': 'CC0 1.0'}, {'license_url': 'https://arxiv.org/abs/2608.10277v2'}, {'caption': 'Invented caption'}, {'url': 'https://arxiv.org/logo.png'},
                       {'license_url': 'https://arxiv.org/help/api'}, {'source_url': 'https://arxiv.org/html/2608.10277v2?other=1'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                figures.register_figure({**manifest(), **change}, self.paper, 'embed', fetcher)

    def test_reject_missing_article_rights_link_and_redirected_article_identity(self):
        def bad_rights(url, maximum):
            raw, mime, final = fetcher(url, maximum)
            return raw.replace(b'Rights to this article', b'Unrelated rights') if mime == 'text/html' else raw, mime, final
        with self.assertRaisesRegex(ValueError, 'article-specific'):
            figures.register_figure(manifest(), self.paper, 'embed', bad_rights)
        def redirect(url, maximum):
            raw, mime, final = fetcher(url, maximum)
            return raw, mime, final.replace('2608.10277', '2608.11111')
        with self.assertRaises(ValueError):figures.register_figure(manifest(), self.paper, 'embed', redirect)
        def version_redirect(url, maximum):
            raw, mime, final = fetcher(url, maximum)
            return raw, mime, final.replace('v1', 'v2') if '/html/' in url else final
        with self.assertRaises(ValueError):figures.register_figure(manifest(), self.paper, 'embed', version_redirect)

    def test_unrelated_cc_link_cannot_override_article_license(self):
        def unrelated(url, maximum):
            raw, mime, final = fetcher(url, maximum)
            if mime == 'text/html':
                raw = raw.replace(b'licenses/by/4.0/', b'licenses/nonexclusive-distrib/1.0/')
                raw += b'<a href="https://creativecommons.org/publicdomain/zero/1.0/">metadata license</a>'
            return raw, mime, final
        with self.assertRaisesRegex(ValueError, 'article-specific'):
            figures.register_figure({**manifest(),'license':'CC0 1.0'}, self.paper, 'embed', unrelated)

    def test_html_math_comparisons_preserve_caption_text(self):
        page = figures._Page(b'<p>x &lt; 3</p><figcaption>Figure 5: Original scientific comparison.</figcaption><p>y &gt; 4</p>', 'https://arxiv.org/html/2608.10277v1')
        self.assertIn('Figure 5: Original scientific comparison.',page.text)

    def test_reject_malformed_raster_mime_and_integrity(self):
        truncated = b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x0dIHDR' + b'\x00\x00\x00\x01' * 2 + b'\x00' * 9
        for raw in (truncated, raster()[:40], b'<svg></svg>', b'<html>not a figure</html>'):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):figures.image_type(raw)
        _, asset = figures.register_figure(manifest(), self.paper, 'embed', fetcher)
        for key, value in [('sha256', 'a' * 64), ('size_bytes', 1), ('content_type', 'text/html'), ('filename', '../bad.png'), ('content_id', 'other')]:
            with self.subTest(key=key), self.assertRaises(ValueError):figures.validate_inline_images([{**asset, key:value}])
        with self.assertRaises(ValueError):figures.validate_inline_images([asset,asset])

    def test_private_multicast_urls_and_mixed_dns_rejected(self):
        for url in ('https://127.0.0.1/x', 'https://224.0.0.1/x', 'https://[::1]/x', 'file:///tmp/a', 'https://x.local/a'):
            self.assertEqual(safe_figure_url(url), '')
        for address in ('127.0.0.1','169.254.169.254','224.0.0.1'):
            with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))]),self.assertRaises(ValueError):
                figures._public_addresses('example.org')

    def test_proxy_bypass_uses_pinned_dns_and_untrusted_proxy_hosts_fail(self):
        with patch.dict(os.environ, {'HTTPS_PROXY':'http://proxy.example.org'}), patch('literature_digest.figures.proxy_bypass',return_value=True), patch('literature_digest.figures._public_addresses',side_effect=ValueError('blocked')) as dns:
            with self.assertRaisesRegex(ValueError,'blocked'):figures.fetch_public('https://arxiv.org/html/2608.10277v1',100)
            dns.assert_called_once()
        with patch.dict(os.environ, {'HTTPS_PROXY':'http://proxy.example.org'}), patch('literature_digest.figures.proxy_bypass',return_value=False):
            with self.assertRaisesRegex(ValueError,'exact official'):figures.fetch_public('https://example.org/x',100)

    def test_renderer_keeps_ten_configured_figures_and_inline_contract(self):
        figure,asset=figures.register_figure(manifest(),self.paper,'embed',fetcher)
        self.paper.figures=[{**figure,'id':str(i)} for i in range(10)]
        rendered=_figures(self.paper,{'images':{'mode':'embed','max_per_paper':10}},'inline')
        self.assertEqual(len(rendered),10);self.assertTrue(all(f['embed']=='cid:'+asset['content_id'] for f in rendered))


class FigureJobLifecycle(unittest.TestCase):
    def setUp(self):
        self.h = test_agent_jobs.AgentJobs(); self.h.setUp(); self.addCleanup(self.h.doCleanups)
        self.h.config['images']={'mode':'embed','max_per_paper':2}
        self.h.paper.arxiv_id='2608.10277'; self.h.paper.doi=''; self.h.paper.source='arxiv'; self.h.paper.source_id='2608.10277'

    def test_registration_path_boundary_and_immutable_finalization(self):
        h=self.h; job=create_job(h.config,h.now,'connector');h.source(job)
        outside=h.root/'figure.json';outside.write_text(json.dumps(manifest()))
        with self.assertRaisesRegex(ValueError,'workspace'):tool(h.config,job['job_id'],'figure',input_path=outside)
        path=Path(job['workspace'])/'figure.json';path.write_text(json.dumps(manifest()))
        with patch('literature_digest.figures.fetch_public',side_effect=fetcher):
            self.assertTrue(tool(h.config,job['job_id'],'figure',input_path=path)['inline_image'])
        result=tool(h.config,job['job_id'],'finalize',input_path=h.submission())
        envelope=json.loads(Path(result['paths']['envelope']).read_text())
        self.assertEqual(len(envelope['inline_images']),1);self.assertIn('cid:figure-',envelope['html'])
        with self.assertRaisesRegex(ValueError,'closed'):tool(h.config,job['job_id'],'figure',input_path=path)

    def test_explicit_revision_preserves_sent_job_and_same_audience_ledger(self):
        h=self.h; job,result=h.finish('connector');state=h.state()
        begin_send(h.config,job['job_id'],now=h.now)
        receipt={'digest_id':job['job_id'],'envelope_sha256':result['envelope_sha256'],'provider':'offline-test','status':'accepted',
                 'sender':'sender@example.org','recipient':h.config['recipient'],'message_id':'message1','accepted_at':h.now.isoformat(),'provider_receipt':{'id':'message1'}}
        confirm_sent(h.config,job['job_id'],receipt)
        original=copy.deepcopy(state.get(job['job_id']))
        snapshot={p:p.read_bytes() for p in Path(job['workspace']).rglob('*') if p.is_file()}
        changed=copy.deepcopy(h.config);changed['images']['max_per_paper']=1
        revision=create_job(changed,h.now,'connector',revision_of=job['job_id'],revision_reason='Add original figures and closing synthesis')
        self.assertNotEqual(revision['job_id'],job['job_id'])
        revised=tool(changed,revision['job_id'],'finalize',input_path=h.submission())
        self.assertEqual(begin_send(changed,revision['job_id'],now=h.now)['status'],'sending')
        self.assertEqual(state.get(job['job_id']),original)
        self.assertTrue(all(path.read_bytes()==raw for path,raw in snapshot.items()))
        self.assertIn('Revised edition',json.loads(Path(revised['paths']['envelope']).read_text())['subject'])
        with self.assertRaises(ValueError):begin_send(changed,revision['job_id'],now=h.now)

    def test_revision_does_not_bypass_unconfirmed_original(self):
        h=self.h;job,result=h.finish('connector')
        with self.assertRaisesRegex(ValueError,'confirmed sent'):
            create_job(h.config,h.now,'connector',revision_of=job['job_id'],revision_reason='Need a revised figure edition')


if __name__=='__main__':unittest.main()
