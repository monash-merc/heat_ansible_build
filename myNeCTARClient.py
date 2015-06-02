
import sys, os, string, subprocess, socket, re
import copy, shlex,uuid, random, multiprocessing, time, shutil, json
import novaclient.v1_1.client as nvclient
import novaclient.exceptions as nvexceptions
from keystoneclient.auth.identity import v2 as v2_auth
from heatclient import client as heat_client

from keystoneclient import session as kssession


class OpenStackConnection:
	
	def __init__(self, username, passwd):
		self.username=username
		self.passwd=passwd
		self.tenantName= os.environ['OS_TENANT_NAME']
		self.tenantID= os.environ['OS_TENANT_ID']
		self.authUrl="https://keystone.rc.nectar.org.au:5000/v2.0"

        def _get_keystone_v2_auth(self, v2_auth_url, **kwargs):
            auth_token = kwargs.pop('auth_token', None)
            tenant_id = kwargs.pop('project_id', None)
            tenant_name = kwargs.pop('project_name', None)
            if auth_token:
                return v2_auth.Token(v2_auth_url, auth_token,
                                     tenant_id=tenant_id,
                                     tenant_name=tenant_name)
            else:
                return v2_auth.Password(v2_auth_url,
                                        username=kwargs.pop('username', None),
                                        password=kwargs.pop('password', None),
                                        tenant_id=tenant_id,
                                        tenant_name=tenant_name)


        def _get_keystone_session(self, **kwargs):
            # first create a Keystone session
            cacert = kwargs.pop('cacert', None)
            cert = kwargs.pop('cert', None)
            key = kwargs.pop('key', None)
            insecure = kwargs.pop('insecure', False)
            timeout = kwargs.pop('timeout', None)
            verify = kwargs.pop('verify', None)

            # FIXME(gyee): this code should come from keystoneclient
            if verify is None:
                if insecure:
                    verify = False
                else:
                    # TODO(gyee): should we do
                    # heatclient.common.http.get_system_ca_fle()?
                    verify = cacert or True
            if cert and key:
                # passing cert and key together is deprecated in favour of the
                # requests lib form of having the cert and key as a tuple
                cert = (cert, key)
            return kssession.Session(verify=verify, cert=cert, timeout=timeout)

        def _get_keystone_auth(self, session, auth_url, **kwargs):
            # FIXME(dhu): this code should come from keystoneclient

            # discover the supported keystone versions using the given url
            v2_auth_url=auth_url
            v3_auth_url=None

            # Determine which authentication plugin to use. First inspect the
            # auth_url to see the supported version. If both v3 and v2 are
            # supported, then use the highest version if possible.
            auth = None
            if v3_auth_url and v2_auth_url:
                user_domain_name = kwargs.get('user_domain_name', None)
                user_domain_id = kwargs.get('user_domain_id', None)
                project_domain_name = kwargs.get('project_domain_name', None)
                project_domain_id = kwargs.get('project_domain_id', None)

                # support both v2 and v3 auth. Use v3 if domain information is
                # provided.
                if (user_domain_name or user_domain_id or project_domain_name or
                        project_domain_id):
                    auth = self._get_keystone_v3_auth(v3_auth_url, **kwargs)
                else:
                    auth = self._get_keystone_v2_auth(v2_auth_url, **kwargs)
            elif v3_auth_url:
                # support only v3
                auth = self._get_keystone_v3_auth(v3_auth_url, **kwargs)
            elif v2_auth_url:
                # support only v2
                auth = self._get_keystone_v2_auth(v2_auth_url, **kwargs)
            else:
                raise exc.CommandError(_('Unable to determine the Keystone '
                                         'version to authenticate with using the '
                                         'given auth_url.'))

            return auth

        def get_stack_name(self,stack):
            stacks=[]
            for s in self.hc.stacks.list():
                stacks.append(s.stack_name)
            if stack in stacks:
                return stack
            elif len(stacks)==1:
                return stacks[0]
            elif len(stacks)==0:
                raise Exception("You do not have any heat stacks in your OpenStack Project")
            else:
                raise Exception("You have multiple heat stacks in your OpenStack Project and I'm not sure which one to use.\n You can select a stack by symlinking to a stack, for example if you have a stack called mycluster do ln -s %s mycluster\n"%stack)

        def auth(self):
		self.nc = nvclient.Client(	auth_url=self.authUrl,
			username=self.username,
			api_key=self.passwd,
			project_id=self.tenantName,
			tenant_id=self.tenantID,
			service_type="compute"
			)
                kwargs = {
                    'insecure': False,
                }
                keystone_session = self._get_keystone_session(**kwargs)

                kwargs = {
                    'username': self.username,
                    'password': self.passwd,
                    'project_id': self.tenantID,
                    'project_name': self.tenantName 
                }

                keystone_auth = self._get_keystone_auth(keystone_session,
                                                    self.authUrl,
                                                    **kwargs)

                heatendpoint = keystone_auth.get_endpoint(keystone_session,service_type='orchestration', region_name=None)
                novaendpoint = keystone_auth.get_endpoint(keystone_session,service_type='compute', region_name=None)


                kwargs = {
                    'username': self.username,
                    'include_pass': False,
                    'session': keystone_session,
                    'auth_url': self.authUrl,
                    'region_name': '',
                    'endpoint_type': 'publicURL',
                    'service_type': 'orchestration',
                    'password': self.passwd,
                    'auth': keystone_auth,
                }
                api_version=1

                self.hc = heat_client.Client(api_version, heatendpoint, **kwargs)
