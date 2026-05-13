#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import requests
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AdsPowerManager:
    """Manages communication with the local AdsPower API."""

    def __init__(self, api_url: str = "http://127.0.0.1:20725", api_key: Optional[str] = None):
        # Try multiple common AdsPower ports
        self.possible_ports = [20725, 50325, 50326, 20726, 8080, 3000, 9090, 5000]
        self.api_key = api_key
        self.session = requests.Session()
        self.api_url = None
        
        # Test which port works
        for port in self.possible_ports:
            test_url = f"http://127.0.0.1:{port}"
            try:
                # Quick test without auth first
                response = self.session.get(f"{test_url}/api/v1/browser/start", timeout=2)
                if response.status_code in [200, 401, 403]:  # 401/403 means endpoint exists but needs auth
                    self.api_url = test_url
                    logger.info(f"✅ AdsPower API found on port {port}")
                    break
            except requests.exceptions.RequestException:
                continue
        
        if not self.api_url:
            logger.warning(f"⚠️ AdsPower API not found on any port {self.possible_ports}. Using default: {api_url}")
            self.api_url = api_url
        
        self.api_url = self.api_url.rstrip('/')
        self.headers: Dict[str, str] = {}
        if api_key:
            self.headers['Authorization'] = f'Bearer {api_key}'

    def _request(self, path: str, method: str = 'GET', **kwargs: Any) -> Dict[str, Any]:
        url = f"{self.api_url}{path}"

        # Try different authentication methods
        auth_methods = [
            {'Authorization': f'Bearer {self.api_key}'},
            {'token': self.api_key},
            {'API-Key': self.api_key},
            {'X-API-Key': self.api_key},
            {'apikey': self.api_key},
        ]

        last_error = None

        # Try each authentication method
        for auth_headers in auth_methods:
            try:
                kwargs_headers = kwargs.pop('headers', {})
                request_headers = {**auth_headers, **kwargs_headers}

                logger.debug(f"AdsPower API request {method} {url} auth={auth_headers} payload={kwargs.get('json') or kwargs.get('params')}")

                if method.upper() == 'GET':
                    response = self.session.get(url, timeout=15, headers=request_headers, **kwargs)
                else:
                    response = self.session.post(url, timeout=15, headers=request_headers, **kwargs)

                response.raise_for_status()
                try:
                    return response.json()
                except ValueError as exc:
                    raise RuntimeError(f"AdsPower API returned invalid JSON for {url}: {exc}") from exc

            except Exception as e:
                last_error = str(e)
                logger.debug(f"AdsPower auth method failed: {auth_headers} - {last_error}")

        # Try query parameter authentication as last resort
        try:
            query_url = f"{url}{'&' if '?' in url else '?'}token={self.api_key}"
            kwargs_headers = kwargs.pop('headers', {})
            request_headers = {**kwargs_headers}

            logger.debug(f"AdsPower API request {method} {query_url} (query auth) payload={kwargs.get('json') or kwargs.get('params')}")

            if method.upper() == 'GET':
                response = self.session.get(query_url, timeout=15, headers=request_headers, **kwargs)
            else:
                response = self.session.post(query_url, timeout=15, headers=request_headers, **kwargs)

            response.raise_for_status()
            try:
                return response.json()
            except ValueError as exc:
                raise RuntimeError(f"AdsPower API returned invalid JSON for {query_url}: {exc}") from exc

        except Exception as e:
            last_error = str(e)
            logger.debug(f"AdsPower query auth failed: {last_error}")

        raise RuntimeError(f"All AdsPower authentication methods failed. Last error: {last_error}")

    def _parse_ws_endpoint(self, result: Dict[str, Any]) -> Optional[str]:
        if not isinstance(result, dict):
            return None

        data = result.get('data') if isinstance(result.get('data'), dict) else result
        if isinstance(data, dict):
            for key in ('wsEndpoint', 'ws', 'cdp', 'webSocketDebuggerUrl', 'debuggerUrl', 'url'):
                value = data.get(key)
                if isinstance(value, str) and value.startswith(('ws://', 'wss://', 'http://', 'https://')):
                    return value

        return None

    def start_browser(
        self,
        profile_id: Optional[str] = None,
        profile_name: Optional[str] = None,
        extra_options: Optional[Dict[str, Any]] = None
    ) -> str:
        """Start the AdsPower browser and return the CDP endpoint."""
        payload: Dict[str, Any] = {}
        if profile_id:
            payload['profile_id'] = profile_id
        if profile_name:
            payload['profile_name'] = profile_name
        if extra_options:
            payload.update(extra_options)

        endpoints = [
            '/api/v1/browser/start',
            '/api/browser/start',
            '/api/v1/start_browser',
            '/api/v1/ads/start',
            '/api/v1/browser/open'
        ]

        last_error: Optional[str] = None
        for endpoint in endpoints:
            try:
                result = self._request(endpoint, method='POST', json=payload)
                ws_endpoint = self._parse_ws_endpoint(result)
                if ws_endpoint:
                    return ws_endpoint
            except Exception as exc:
                last_error = str(exc)
                logger.debug(f"AdsPower start_browser failed for {endpoint}: {last_error}")

        raise RuntimeError(
            "Unable to start the AdsPower browser. "
            f"Check that AdsPower is running on port 50325 and that the local API endpoint is correct. "
            f"Last error: {last_error}"
        )
