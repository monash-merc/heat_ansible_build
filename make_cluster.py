import yaml
import traceback
import random
import string
import subprocess
import time
import os
import threading
import sys
import ConfigParser
import myNeCTARClient

def new_pass(length):
    return ''.join(random.choice(string.ascii_uppercase + string.digits+string.ascii_lowercase) for _ in range(length))

def check_keystone_vars():
    var_list=['OS_PASSWORD','OS_TENANT_NAME','OS_AUTH_URL']
    env=os.environ
    for v in var_list:
        if not env.has_key(v):
            errmsg="""
I cound't find eht environemtn variable set yb loading your NeCTAR OpenStack RC file.
You can download your RC file by going to the NeCTAR dashboard
Selecting the appropriate tenancy
clicking (on the left hand menu) access and security
selecting the tab "API Access"
clicking download OpenStack RC file.

You will also need your KeyStone Password.
Select at the top right, the dropdown that contains your email address
Select Settings
On the left select "Reset Password"
"""
            raise Exception(errmsg)

def check_nova_installed():
    try:
        p=subprocess.Popen(['nova','help'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        (stdout,stderr)=p.communicate()
    except:
        errmsg="""
I couldn't execute the nova command. You should install python-novaclient either from their git repository
or via your system package manager. 
For Ubuntu you can do sudo apt-get install python-novaclient
"""
        raise Exception(errmsg)

def init_secgroup(nc,name,description):
    secgroup = nc.security_groups.create(name,description)
    print secgroup
    return secgroup

def create_sec_group(nc,name,description,rules):
    print "initiliing secgroup"
    secgroup = init_secgroup(nc,name,description)
    print "inited secgroup"
    ruleparts={'ip_proto':'protocol','from_port':'port_range_min','to_port':'port_range_max','cidr':'remote_ip_prefix'}
    for r in rules:
        rule={}
        for p in ruleparts.keys():
            if r[ruleparts[p]]!=None:
                rule[p]=r[ruleparts[p]]
            else:
                rule[p] = None
        print rule
        nc.security_group_rules.create(secgroup.id,rule['ip_proto'],int(rule['from_port']),int(rule['to_port']),rule['cidr'])
        print "adding rule"

def update_sec_group(nc,name,rules):
    print "updating %s NOT IMPLEMENTED Assume secgroup is already correct"%name

def check_sec_groups(hotfile):
    # Currently NeCTAR does not support neutron, so sec groups in the main HOT file are impossible, However
    # we can create secgroups using nova rather than neutron, but we put them in an auxilary HOT file
    username = os.environ['OS_USERNAME']
    passwd = os.environ['OS_PASSWORD']
    nectar=myNeCTARClient.OpenStackConnection(username,passwd)
    nectar.auth()
    secgroup_list = nectar.nc.security_groups.list()
    f = open(hotfile,'r')
    d=yaml.load(f.read())
    try:
        for rname in d['resources'].keys():
            r=d['resources'][rname]
            if r['type'] == 'OS::Neutron::SecurityGroup':
                name=r['properties']['name']
                try:
                    description=r['properties']['description']
                except:
                    description='no description given'
                rules=r['properties']['rules']
                print r

                found=False
                for s in secgroup_list: 
                    if s.name == name:
                        found=True
                if found:
                    update_sec_group(nectar.nc,name,rules)
                else:
                    print "calling create_sec_group"
                    create_sec_group(nectar.nc,name,description,rules)
    except Exception as e:
        import traceback
        print e
        print traceback.format_exc()
        pass

def check_heat_installed():
    try:
        p=subprocess.Popen(['heat','help'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        (stdout,stderr)=p.communicate()
    except:
        errmsg="""
I couldn't execute the heat command. You should install python-heatclient either from their git repository
or via your system package manager. 
For Ubuntu you can do sudo apt-get install python-novaclient
"""
        raise Exception(errmsg)

def check_ansible_installed():
    try:
        p=subprocess.Popen(['ansible-playbook','--help'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        (stdout,stderr)=p.communicate()
    except:
        errmsg="""
I couldn't find a copy of ansible-playbook. You can either download the latest from git or try to
sudo apt-get install ansible
You might also need the package python-paramiko
"""
        raise Exception(errmsg)

def check_ldap_config(conffile):
    print("check not implemented")

def check_keypairs(hotfile):
    f = open(hotfile,'r')
    d=yaml.load(f.read())
    msg="""
Check for ssh keypairs is not fully implmeneted
Make sure that 
    a) the keypair in your HOT file is also listed by the output of nova keypair-list
    b) The same keypair is loaded into your ssh-agent
"""
    print msg

def write_names_file(filename,clustername,domainname):
    data = {'domain':domainname, 'clustername':clustername}
    f=open(filename,'w+')
    f.write(yaml.dump(data,default_flow_style=False,explicit_start=True))
    f.close()

def check_ansible_config():
    config=ConfigParser.ConfigParser()
    configpath=os.path.expanduser('~/.ansible.cfg')
    changed=False
    values={'remote_tmp':'/tmp/.ansible/tmp','host_key_checking':'False'}
    try:
        config.read([configpath])
    except Exception as e:
        pass
    for key in values.keys():
        try: 
            config_val=config.get('defaults',key)
            if config_val != values[key]:
                config.set('defaults',key,values[key])
                changed=True
        except ConfigParser.NoSectionError as e:
            config.add_section('defaults')
            config.set('defaults',key,values[key])
            changed=True
        except ConfigParser.NoOptionError as e:
            config.set('defaults',key,values[key])
            changed=True

    if changed:
        print "I have set some new values in ~/.ansible.cfg. If this isn't want you want, beware"
        config.write(open(configpath,'w'))



def write_passwd_file(clustername,required_passwords,filename):
    changed=False
        
    pwpath=filename
    try:
        f=open(pwpath,'r')
        data=yaml.load(f.read())
        f.close()
    except Exception as e:
        data={}

    for pw in required_passwords.keys():
        if data.has_key(pw):
            pass
        else:
            data[pw]=new_pass(required_passwords[pw])
            changed=True
    if changed:
        f=open(pwpath,'w+')
        f.write(yaml.safe_dump(data,default_flow_style=False,explicit_start=True))
        f.close()


def create_or_update_stack(clustername,hot_file):
    p = subprocess.Popen(['heat','stack-list'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (stdout,stderr) = p.communicate()
    print "looking for stack %s"%clustername
    if ' %s '%clustername in stdout:
        updating = True
        print "stack found, updating"
    else:
        updating = False
        print "stack not found, creating"
    if updating:
        p = subprocess.Popen(['heat','stack-update',clustername,'-r','-f',hot_file],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        (stdout,stderr) = p.communicate()
    else:
        p = subprocess.Popen(['heat','stack-create',clustername,'-f',hot_file],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        (stdout,stderr) = p.communicate()
    if stderr!=None and stderr!="":
        print("heat failed for some reason")
        print "%s"%stderr
        raise Exception("heat failed")

def get_names(name=None):
    if name!=None:
        return (name,"cvl.massive.org.au")
    else:
        raise Exception("no stack name given")

def wait_for_cluster(clustername):
    complete=False
    while not complete:
        p = subprocess.Popen(['heat','stack-show',clustername],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        (stdout,stderr)=p.communicate()
        if 'CREATE_COMPLETE' in stdout or 'UPDATE_COMPLETE' in stdout:
            complete=True
        if 'FAILED' in stdout:
            print("heat failed for some reason")
            raise Exception("heat failed")
        time.sleep(5)

def readpipe(pipe):
    for l in pipe.readlines():
        print l

def link_inventory(clustername):
    p = subprocess.Popen(['rm','-rf',clustername])
    p.communicate()
    p = subprocess.Popen(['ln','-s',os.path.expanduser('./ansible_cluster_in_a_box/dynamicInventory'),clustername],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (stdout,stderr)=p.communicate()
    if stderr!=None and stderr!="":
        print("linking the inventory failed for some reason")
        print "%s"%stderr
        raise Exception("link_inventory failed")

def run_ansible(inventory,playbook,passwd_file,ldapConfig_file,vars_file,names_file):
    import pty
    if ldapConfig_file!=None:
        cmd='ansible-playbook -i {inventory} {playbook} --extra-vars @{passwd_file} --extra-vars @{ldapConfig_file} --extra-vars @{vars_file} --extra-vars @{names_file}'.format(inventory=inventory,playbook=playbook,passwd_file=passwd_file,ldapConfig_file=ldapConfig_file,vars_file=vars_file,names_file=names_file)
    else:
        cmd='ansible-playbook_asdf -i {inventory} {playbook} --extra-vars @{passwd_file} --extra-vars @{vars_file} --extra-vars @{names_file}'.format(inventory=inventory,playbook=playbook,passwd_file=passwd_file,vars_file=vars_file,names_file=names_file)
    print "Now run the command %s"%cmd




def main():
    if len(sys.argv) >1 :
        stackname = sys.argv[1]
    else:
        stackname=None
    try:
        config=ConfigParser.ConfigParser()
        configpath=os.path.expanduser('./cluster_config.cfg')
        changed=False
        try:
            config.read([configpath])
        except Exception as e:
            pass
        passwd_file=config.get('defaults','passwd_file')
        clustername=config.get('defaults','name')
        if stackname == None:
            stackname=clustername
        domain=config.get('defaults','domain')
        vars_file=config.get('defaults','vars')
        names_file=config.get('defaults','names_file')
        hot_file=config.get('defaults','hot_file')
        playbook=config.get('defaults','playbook')
        reqpasswdstr = config.get('defaults','reqpasswd')
        try:
            secgroup_hot_file=config.get('defaults','secgroup_hot_file')
        except:
            secgroup_hot_file=None
        import json
        reqpasswd = json.loads(reqpasswdstr)
        try:
            ldapConfig_file=config.get('defaults','ldapconfig_file')
            ldapConfig_file=os.path.abspath(ldapConfig_file)
        except:
            ldapConfig_file=None

        passwd_file = os.path.abspath(passwd_file)
        vars_file = os.path.abspath(vars_file)
        names_file = os.path.abspath(names_file)
        hot_file = os.path.abspath(hot_file)
        playbook = os.path.abspath(playbook)
        check_keystone_vars()
        check_nova_installed()
        check_heat_installed()
        if secgroup_hot_file!=None:
            check_sec_groups(secgroup_hot_file)
        check_keypairs(hot_file)
        check_ansible_config()
        check_ansible_installed()
        if ldapConfig_file !=None:
            check_ldap_config(ldapConfig_file)
        write_names_file(names_file,clustername,domain)
        write_passwd_file(clustername,reqpasswd,passwd_file)
        create_or_update_stack(stackname,hot_file)
        link_inventory(stackname)
        wait_for_cluster(stackname)
        print("extra wait")
        time.sleep(3)
        run_ansible(os.path.abspath(stackname),playbook,passwd_file,ldapConfig_file,vars_file,names_file)
    except Exception as e:
        print traceback.format_exc()
        print e
        print("Can not continue creating your cluster, please see error messages above")



main()
