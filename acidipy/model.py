'''
Created on 2016. 10. 18.

@author: "comfact"
'''

import re
import ssl
import json

from websocket import create_connection

from .common import SystemThread, SchedTask, Scheduler
from .session import Session
from .static import *

###############################################################
#  ________  ________ _________  ________  ________     
# |\   __  \|\   ____\\___   ___\\   __  \|\   __  \    
# \ \  \|\  \ \  \___\|___ \  \_\ \  \|\  \ \  \|\  \   
#  \ \   __  \ \  \       \ \  \ \ \  \\\  \ \   _  _\  
#   \ \  \ \  \ \  \____   \ \  \ \ \  \\\  \ \  \\  \| 
#    \ \__\ \__\ \_______\  \ \__\ \ \_______\ \__\\ _\ 
#     \|__|\|__|\|_______|   \|__|  \|_______|\|__|\|__|
#                                                       
###############################################################

#===============================================================================
# Subscribe Actor
#===============================================================================
class SubscribeActor:
    
    def subscribe(self, handler):
        handler.class_name = self.class_name
        self.controller.subscriber.register(handler)

#===============================================================================
# Class Actor
#===============================================================================
class AcidipyActor:
    
    def __init__(self, parent, class_name, class_pkey=None, class_ident=None):
        self.parent = parent
        self.controller = parent.controller
        self.class_name = class_name
        self.class_pkey = class_pkey
        self.class_ident = class_ident
        if class_name in PREPARE_CLASSES: self.prepare_class = globals()[PREPARE_CLASSES[class_name]]
        else: self.prepare_class = None

    def list(self, detail=False, sort=None, page=None, **clause):
        url = '/api/mo/' + self.parent['dn'] + '.json?query-target=subtree&target-subtree-class=' + self.class_name
        if not detail: url += '&rsp-prop-include=naming-only'
        if len(clause) > 0:
            url += '&query-target-filter=and('
            for key in clause: url += 'eq(%s.%s,"%s"),' % (self.class_name, key, clause[key])
            url += ')'
        if sort != None:
            url += '&order-by='
            if isinstance(sort, list):
                for s in sort: url += self.class_name + ('.%s,' % s)
            else: url += self.class_name + ('.%s' % sort)
        if page != None:
            url += '&page=%d&page-size=%d' % (page[0], page[1])
        data = self.controller.get(url)
        ret = []
        for d in data:
            for class_name in d:
                acidipy_obj = AcidipyObject(**d[class_name]['attributes'])
                acidipy_obj.class_name = class_name
                acidipy_obj.controller = self.controller
                acidipy_obj.is_detail = detail
                if self.prepare_class:
                    acidipy_obj.__class__ = self.prepare_class
                    acidipy_obj.__patch__()
                ret.append(acidipy_obj)
        return ret
    
    def __call__(self, rn, detail=False):
        url = '/api/mo/' + self.parent['dn'] + (self.class_ident % rn) + '.json'
        if not detail: url += '?rsp-prop-include=naming-only'
        data = self.controller.get(url)
        for d in data:
            for class_name in d:
                acidipy_obj = AcidipyObject(**d[class_name]['attributes'])
                acidipy_obj.controller = self.controller
                acidipy_obj.class_name = class_name
                acidipy_obj.is_detail = detail
                if self.prepare_class:
                    acidipy_obj.__class__ = self.prepare_class
                    acidipy_obj.__patch__()
                return acidipy_obj
        raise AcidipyNonExistData(self.parent['dn'] + (self.class_ident % rn))
    
    def count(self):
        url = '/api/node/class/' + self.class_name + '.json?query-target-filter=wcard(' + self.class_name + '.dn,"' + self.parent['dn'] + '/.*")&rsp-subtree-include=count'
        data = self.controller.get(url)
        try: return int(data[0]['moCount']['attributes']['count'])
        except: raise AcidipyNonExistCount(self.class_name)

class AcidipyActorHealth:

    def health(self):
        url = '/api/node/class/' + self.class_name + '.json?query-target-filter=wcard(' + self.class_name + '.dn,"' + self.parent['dn'] + '/.*")&rsp-subtree-include=health'
        data = self.controller.get(url)
        ret = []
        for d in data:
            for class_name in d:
                try: hinst = d[class_name]['children'][0]['healthInst']
                except: continue
                attrs = d[class_name]['attributes']
                obj = {'dn' : attrs['dn'], 'name' : attrs['name'], 'score' : int(hinst['attributes']['cur'])}
                ret.append(obj)
        return ret
    
class AcidipyActorCreate:
    
    def create(self, **attributes):
        acidipy_obj = AcidipyObject(**attributes)
        acidipy_obj.class_name = self.class_name
        if self.controller.post('/api/mo/' + self.parent['dn'] + '.json', acidipy_obj.toJson()):
            acidipy_obj.controller = self.controller
            acidipy_obj['dn'] = self.parent['dn'] + (self.class_ident % attributes[self.class_pkey])
            acidipy_obj.is_detail = False
            if self.prepare_class:
                acidipy_obj.__class__ = self.prepare_class
                acidipy_obj.__patch__()
            return acidipy_obj
        raise AcidipyCreateError(self.class_name)

class TenantActor(AcidipyActor, AcidipyActorHealth, AcidipyActorCreate, SubscribeActor):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'fvTenant', 'name', '/tn-%s')
    
class FilterActor(AcidipyActor, AcidipyActorCreate):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'vzFilter', 'name', '/flt-%s')

class ContractActor(AcidipyActor, AcidipyActorCreate):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'vzBrCP', 'name', '/brc-%s')

class ContextActor(AcidipyActor, AcidipyActorHealth, AcidipyActorCreate):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'fvCtx', 'name', '/ctx-%s')
    
class L3ExternalActor(AcidipyActor, AcidipyActorCreate):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'l3extOut', 'name', '/out-%s')
    
class BridgeDomainActor(AcidipyActor, AcidipyActorHealth, AcidipyActorCreate):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'fvBD', 'name', '/BD-%s')

class AppProfileActor(AcidipyActor, AcidipyActorHealth, AcidipyActorCreate):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'fvAp', 'name', '/ap-%s')

class FilterEntryActor(AcidipyActor, AcidipyActorCreate):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'vzEntry', 'name', '/e-%s')

class SubjectActor(AcidipyActor, AcidipyActorCreate):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'vzSubj', 'name', '/subj-%s')

class SubnetActor(AcidipyActor, AcidipyActorCreate):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'fvSubnet', 'ip', '/subnet-[%s]')

class EPGActor(AcidipyActor, AcidipyActorHealth, AcidipyActorCreate):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'fvAEPg', 'name', '/epg-%s')

class EndpointActor(AcidipyActor, AcidipyActorCreate):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'fvCEp', 'name', '/cep-%s')

class PodActor(AcidipyActor, SubscribeActor):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'fabricPod', 'id', '/pod-%s')
    def health(self):
        url = '/api/node/class/fabricHealthTotal.json?query-target-filter=ne(fabricHealthTotal.dn,"topology/health")'
        data = self.controller.get(url)
        ret = []
        for d in data:
            for class_name in d:
                attrs = d[class_name]['attributes']
                if self.parent['dn'] in attrs['dn']:
                    obj = {'dn' : attrs['dn'].replace('/health', ''), 'name' : attrs['dn'].split('/')[1].replace('pod-', ''), 'score' : int(attrs['cur'])}
                    ret.append(obj)
        return ret

class NodeActor(AcidipyActor):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'fabricNode', 'id', '/node-%s')
    def health(self):
        url = '/api/node/class/healthInst.json?query-target-filter=wcard(healthInst.dn,"^sys/health")'
        data = self.controller.get(url)
        ret = []
        for d in data:
            for class_name in d:
                attrs = d[class_name]['attributes']
                if self.parent['dn'] in attrs['dn']:
                    obj = {'dn' : attrs['dn'].replace('/sys/health', ''), 'name' : attrs['dn'].split('/')[2].replace('node-', ''), 'score' : int(attrs['cur'])}
                    ret.append(obj)
        return ret
    
class PathsActor(AcidipyActor):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'fabricPathEpCont', 'nodeId', '/paths-%s')

class VPathsActor(AcidipyActor):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'fabricProtPathEpCont', 'nodeId', '/protpaths-%s')

class PathActor(AcidipyActor):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'fabricPathEp', 'name', '/pathep-[%s]')
    
class PhysIfActor(AcidipyActor):
    def __init__(self, parent): AcidipyActor.__init__(self, parent, 'l1PhysIf', 'id', '/phys-[%s]')
    def health(self):
        url = '/api/node/class/healthInst.json?query-target-filter=wcard(healthInst.dn,"phys/health")'
        data = self.controller.get(url)
        ret = []
        for d in data:
            for class_name in d:
                attrs = d[class_name]['attributes']
                if self.parent['dn'] in attrs['dn']:
                    obj = {'dn' : attrs['dn'].replace('/phys/health', ''), 'name' : attrs['dn'].split('[')[1].replace(']/phys/health', ''), 'score' : int(attrs['cur'])}
                    ret.append(obj)
        return ret

#===============================================================================
# Controller Actor
#===============================================================================
class ControllerActor:
        
    def __init__(self, controller, class_name):
        self.controller = controller
        self.class_name = class_name
        if class_name in PREPARE_CLASSES: self.prepare_class = globals()[PREPARE_CLASSES[class_name]]
        else: self.prepare_class = None
        
    def list(self, detail=False, sort=None, page=None, **clause):
        url = '/api/node/class/' + self.class_name + '.json?'
        if not detail: url += '&rsp-prop-include=naming-only'
        if len(clause) > 0:
            url += '&query-target-filter=and('
            for key in clause: url += 'eq(%s.%s,"%s"),' % (self.class_name, key, clause[key])
            url += ')'
        if sort != None:
            url += '&order-by='
            if isinstance(sort, list):
                for s in sort: url += self.class_name + ('.%s,' % s)
            else: url += self.class_name + ('.%s' % sort)
        if page != None:
            url += '&page=%d&page-size=%d' % (page[0], page[1])
        data = self.controller.get(url)
        ret = []
        for d in data:
            for class_name in d:
                acidipy_obj = AcidipyObject(**d[class_name]['attributes'])
                acidipy_obj.class_name = class_name
                acidipy_obj.controller = self.controller
                acidipy_obj.is_detail = detail
                if self.prepare_class:
                    acidipy_obj.__class__ = self.prepare_class
                    acidipy_obj.__patch__()
                ret.append(acidipy_obj)
        return ret
    
    def count(self):
        url = '/api/node/class/' + self.class_name + '.json?rsp-subtree-include=count'
        data = self.controller.get(url)
        try: return int(data[0]['moCount']['attributes']['count'])
        except: raise AcidipyNonExistCount(self.class_name)
        
class ControllerActorHealth:
    
    def health(self):
        url = '/api/node/class/' + self.class_name + '.json?&rsp-subtree-include=health'
        data = self.controller.get(url)
        ret = []
        for d in data:
            for class_name in d:
                try: hinst = d[class_name]['children'][0]['healthInst']
                except: continue
                attrs = d[class_name]['attributes']
                obj = {'dn' : attrs['dn'], 'name' : attrs['name'], 'score' : int(hinst['attributes']['cur'])}
                ret.append(obj)
        return ret

class ControllerFilterActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'vzFilter')

class ControllerContractActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'vzBrCP')

class ControllerContextActor(ControllerActor, ControllerActorHealth, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'fvCtx')

class ControllerL3ExternalActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'l3extOut')
    
class ControllerBridgeDomainActor(ControllerActor, ControllerActorHealth, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'fvBD')

class ControllerAppProfileActor(ControllerActor, ControllerActorHealth, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'fvAp')

class ControllerFilterEntryActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'vzEntry')

class ControllerSubjectActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'vzSubj')

class ControllerSubnetActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'fvSubnet')

class ControllerEPGActor(ControllerActor, ControllerActorHealth, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'fvAEPg')
    
class ControllerEndpointActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'fvCEp')
    
class ControllerNodeActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'fabricNode')
    def health(self):
        url = '/api/node/class/healthInst.json?query-target-filter=wcard(healthInst.dn,"^sys/health")'
        data = self.controller.get(url)
        ret = []
        for d in data:
            for class_name in d:
                attrs = d[class_name]['attributes']
                obj = {'dn' : attrs['dn'].replace('/sys/health', ''), 'name' : attrs['dn'].split('/')[2].replace('node-', ''), 'score' : int(attrs['cur'])}
                ret.append(obj)
        return ret

class ControllerPathsActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'fabricPathEpCont')

class ControllerVPathsActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'fabricProtPathEpCont')

class ControllerPathActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'fabricPathEp')

class ControllerSystemActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'topSystem')

class ControllerPhysIfActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'l1PhysIf')
    def health(self):
        url = '/api/node/class/healthInst.json?query-target-filter=wcard(healthInst.dn,"phys/health")'
        data = self.controller.get(url)
        ret = []
        for d in data:
            for class_name in d:
                attrs = d[class_name]['attributes']
                obj = {'dn' : attrs['dn'].replace('/phys/health', ''), 'name' : attrs['dn'].split('[')[1].replace(']/phys/health', ''), 'score' : int(attrs['cur'])}
                ret.append(obj)
        return ret

class ControllerFaultActor(ControllerActor, SubscribeActor):
    def __init__(self, controller): ControllerActor.__init__(self, controller, 'faultInfo')

########################################################################################
#  ________  ________  ________  _________  ________  ________  ________ _________   
# |\   __  \|\   __  \|\   ____\|\___   ___\\   __  \|\   __  \|\   ____\\___   ___\ 
# \ \  \|\  \ \  \|\ /\ \  \___|\|___ \  \_\ \  \|\  \ \  \|\  \ \  \___\|___ \  \_| 
#  \ \   __  \ \   __  \ \_____  \   \ \  \ \ \   _  _\ \   __  \ \  \       \ \  \  
#   \ \  \ \  \ \  \|\  \|____|\  \   \ \  \ \ \  \\  \\ \  \ \  \ \  \____   \ \  \ 
#    \ \__\ \__\ \_______\____\_\  \   \ \__\ \ \__\\ _\\ \__\ \__\ \_______\  \ \__\
#     \|__|\|__|\|_______|\_________\   \|__|  \|__|\|__|\|__|\|__|\|_______|   \|__|
#                        \|_________|                                                
#
########################################################################################

class AcidipyObject(dict):
    
    def __init__(self, **attributes):
        dict.__init__(self, **attributes)
    
    def __patch__(self):
        pass
    
    def toJson(self):
        data = {}
        data[self.class_name] = {'attributes' : self}
        return json.dumps(data, sort_keys=True)
    
    def detail(self):
        if not self.is_detail:
            url = '/api/mo/' + self['dn'] + '.json'
            data = self.controller.get(url)
            for d in data:
                for class_name in d:
                    attrs = d[class_name]['attributes']
                    for key in attrs: self[key] = attrs[key]
            self.is_detail = True
        return self

class AcidipyObjectParent:
    
    def parent(self, detail=False):
        try: parent_dn = self['dn'].split(re.match('[\W\w]+(?P<rn>/\w+-\[?[\W\w]+]?)$', self['dn']).group('rn'))[0]
        except: raise AcidipyNonExistParent(self['dn'])
        url = '/api/mo/' + parent_dn + '.json'
        if not detail: url += '?rsp-prop-include=naming-only'
        data = self.controller.get(url)
        for d in data:
            for class_name in d:
                acidipy_obj = AcidipyObject(**d[class_name]['attributes'])
                acidipy_obj.controller = self.controller
                acidipy_obj.class_name = class_name
                acidipy_obj.is_detail = detail
                if class_name in PREPARE_CLASSES:
                    acidipy_obj.__class__ = globals()[PREPARE_CLASSES[class_name]]
                    acidipy_obj.__patch__()
                return acidipy_obj
        raise AcidipyNonExistData(parent_dn)

class AcidipyObjectChildren:
    
    def children(self, detail=False, sort=None, page=None, **clause):
        url = '/api/mo/' + self['dn'] + '.json?query-target=children'
        if not detail: url += '&rsp-prop-include=naming-only'
        if len(clause) > 0:
            url += '&query-target-filter=and('
            for key in clause: url += 'eq(%s.%s,"%s"),' % (self.class_name, key, clause[key])
            url += ')'
        if sort != None:
            url += '&order-by='
            if isinstance(sort, list):
                for s in sort: url += self.class_name + ('.%s,' % s)
            else: url += self.class_name + ('.%s' % sort)
        if page != None:
            url += '&page=%d&page-size=%d' % (page[0], page[1])
        data = self.controller.get(url)
        ret = []
        for d in data:
            for class_name in d:
                acidipy_obj = AcidipyObject(**d[class_name]['attributes'])
                acidipy_obj.class_name = class_name
                acidipy_obj.controller = self.controller
                acidipy_obj.is_detail = detail
                if class_name in PREPARE_CLASSES:
                    acidipy_obj.__class__ = globals()[PREPARE_CLASSES[class_name]]
                    acidipy_obj.__patch__()
                ret.append(acidipy_obj)
        return ret

class AcidipyObjectHealth:
    
    def health(self):
        url = '/api/mo/' + self['dn'] + '.json?rsp-subtree-include=health'
        data = self.controller.get(url)
        for d in data:
            for class_name in d:
                try: hinst = d[class_name]['children'][0]['healthInst']
                except: continue
                return {'dn' : self['dn'], 'name' : self['name'], 'score' : int(hinst['attributes']['cur'])}
        raise AcidipyNonExistHealth(self['dn'])

class AcidipyObjectModify:
    
    def update(self):
        if not self.controller.put('/api/mo/' + self['dn'] + '.json', data=self.toJson()): raise AcidipyUpdateError(self['dn'])
        return True
    
    def delete(self):
        if not self.controller.delete('/api/mo/' + self['dn'] + '.json'): raise AcidipyDeleteError(self['dn'])
        return True

###############################################################
#  _____ ______   ________  ________  _______   ___          
# |\   _ \  _   \|\   __  \|\   ___ \|\  ___ \ |\  \         
# \ \  \\\__\ \  \ \  \|\  \ \  \_|\ \ \   __/|\ \  \        
#  \ \  \\|__| \  \ \  \\\  \ \  \ \\ \ \  \_|/_\ \  \       
#   \ \  \    \ \  \ \  \\\  \ \  \_\\ \ \  \_|\ \ \  \____  
#    \ \__\    \ \__\ \_______\ \_______\ \_______\ \_______\
#     \|__|     \|__|\|_______|\|_______|\|_______|\|_______|
#
###############################################################

#===============================================================================
# Uni Models
#===============================================================================
class TenantObject(AcidipyObject, AcidipyObjectChildren, AcidipyObjectHealth, AcidipyObjectModify):
    
    def __patch__(self):
        self.Filter = FilterActor(self)
        self.Contract = ContractActor(self)
        self.Context = ContextActor(self)
        self.L3External = L3ExternalActor(self)
        self.BridgeDomain = BridgeDomainActor(self)
        self.AppProfile = AppProfileActor(self)
        
class FilterObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren, AcidipyObjectModify):
    
    def __patch__(self):
        self.FilterEntry = FilterEntryActor(self)

class ContractObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren, AcidipyObjectModify):
    
    def __patch__(self):
        self.Subject = SubjectActor(self)

class ContextObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren, AcidipyObjectHealth, AcidipyObjectModify): pass
     
class L3ExternalObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren, AcidipyObjectModify):
    
    def relate2Context(self, vrf_object, **attributes):
        if isinstance(vrf_object, ContextObject):
            attributes['tnFvCtxName'] = vrf_object['name']
            if self.controller.post('/api/mo/' + self['dn'] + '.json', data=json.dumps({'l3extRsEctx' : {'attributes' : attributes}})): return True
        raise AcidipyRelateError(self['dn'] + ' << >> ' + vrf_object['dn'])

class BridgeDomainObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren, AcidipyObjectHealth, AcidipyObjectModify):
     
    def __patch__(self):
        self.Subnet = SubnetActor(self)
         
    def relate2Context(self, vrf_object, **attributes):
        if isinstance(vrf_object, ContextObject):
            attributes['tnFvCtxName'] = vrf_object['name']
            if self.controller.post('/api/mo/' + self['dn'] + '.json', data=json.dumps({'fvRsCtx' : {'attributes' : attributes}})): return True
        raise AcidipyRelateError(self['dn'] + ' << >> ' + vrf_object['dn'])
    
    def relate2L3External(self, out_object, **attributes):
        if isinstance(out_object, L3ExternalObject):
            attributes['tnL3extOutName'] = out_object['name']
            if self.controller.post('/api/mo/' + self['dn'] + '.json', data=json.dumps({'fvRsBDToOut' : {'attributes' : attributes}})): return True
        raise AcidipyRelateError(self['dn'] + ' << >> ' + out_object['dn']) 
 
class AppProfileObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren, AcidipyObjectHealth, AcidipyObjectModify):
     
    def __patch__(self):
        self.EPG = EPGActor(self)

class FilterEntryObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren, AcidipyObjectModify): pass

class SubjectObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren, AcidipyObjectModify):
    
    def relate2Filter(self, flt_object, **attributes):
        if isinstance(flt_object, FilterObject):
            attributes['tnVzFilterName'] = flt_object['name']
            if self.controller.post('/api/mo/' + self['dn'] + '.json', data=json.dumps({'vzRsSubjFiltAtt' : {'attributes' : attributes}})): return True
        raise AcidipyRelateError(self['dn'] + ' << >> ' + flt_object['dn'])
         
class SubnetObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren, AcidipyObjectModify): pass
     
class EPGObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren, AcidipyObjectHealth, AcidipyObjectModify):
    
    def __patch__(self):
        self.Endpoint = EndpointActor(self)
     
    def relate2BridgeDomain(self, bd_object, **attributes):
        if isinstance(bd_object, BridgeDomainObject):
            attributes['tnFvBDName'] = bd_object['name']
            if self.controller.post('/api/mo/' + self['dn'] + '.json', data=json.dumps({'fvRsBd' : {'attributes' : attributes}})): return True
        raise AcidipyRelateError(self['dn'] + ' << >> ' + bd_object['dn'])
    
    def relate2Provider(self, ctr_object, **attributes):
        if isinstance(ctr_object, ContractObject):
            attributes['tnVzBrCPName'] = ctr_object['name']
            if self.controller.post('/api/mo/' + self['dn'] + '.json', data=json.dumps({'fvRsProv' : {'attributes' : attributes}})): return True
        raise AcidipyRelateError(self['dn'] + ' << >> ' + ctr_object['dn'])
    
    def relate2Consumer(self, ctr_object, **attributes):
        if isinstance(ctr_object, ContractObject):
            attributes['tnVzBrCPName'] = ctr_object['name']
            if self.controller.post('/api/mo/' + self['dn'] + '.json', data=json.dumps({'fvRsCons' : {'attributes' : attributes}})): return True
        raise AcidipyRelateError(self['dn'] + ' << >> ' + ctr_object['dn'])
    
    def relate2StaticPath(self, path_object, encap, **attributes):
        if isinstance(path_object, PathObject):
            attributes['tDn'] = path_object['dn']
            attributes['encap'] = encap
            if self.controller.post('/api/mo/' + self['dn'] + '.json', data=json.dumps({'fvRsPathAtt' : {'attributes' : attributes}})): return True
        raise AcidipyRelateError(self['dn'] + ' << >> ' + path_object['dn'])

class EndpointObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren): pass

#===============================================================================
# Topo Models
#===============================================================================
class PodObject(AcidipyObject, AcidipyObjectChildren):
    
    def __patch__(self):
        self.Node = NodeActor(self)
        self.Paths = PathsActor(self)
        self.VPaths = VPathsActor(self)

class NodeObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren):
    
    def __patch__(self):
        if self['fabricSt'] == 'active':
            if self.is_detail: self.System = SystemObject(**self.controller(self['dn'] + '/sys', detail=self.is_detail))
            else: self.System = SystemObject(dn=self['dn'] + '/sys')
            self.System.controller = self.controller
            self.System.is_detail = self.is_detail
            self.System.__patch__()

class SystemObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren):
        
    def __patch__(self):
        self.PhysIf = PhysIfActor(self)
        
class PathsObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren):
    
    def __patch__(self):
        self.Path = PathActor(self)
        
class VPathsObject(AcidipyObject, AcidipyObjectParent, AcidipyObjectChildren):
    
    def __patch__(self):
        self.Path = PathActor(self)

class PathObject(AcidipyObject, AcidipyObjectParent): pass

class PhysIfObject(AcidipyObject, AcidipyObjectParent): pass
        

#############################################################################################################
#  ________  ________  ________   _________  ________  ________  ___       ___       _______   ________     
# |\   ____\|\   __  \|\   ___  \|\___   ___\\   __  \|\   __  \|\  \     |\  \     |\  ___ \ |\   __  \    
# \ \  \___|\ \  \|\  \ \  \\ \  \|___ \  \_\ \  \|\  \ \  \|\  \ \  \    \ \  \    \ \   __/|\ \  \|\  \   
#  \ \  \    \ \  \\\  \ \  \\ \  \   \ \  \ \ \   _  _\ \  \\\  \ \  \    \ \  \    \ \  \_|/_\ \   _  _\  
#   \ \  \____\ \  \\\  \ \  \\ \  \   \ \  \ \ \  \\  \\ \  \\\  \ \  \____\ \  \____\ \  \_|\ \ \  \\  \| 
#    \ \_______\ \_______\ \__\\ \__\   \ \__\ \ \__\\ _\\ \_______\ \_______\ \_______\ \_______\ \__\\ _\ 
#     \|_______|\|_______|\|__| \|__|    \|__|  \|__|\|__|\|_______|\|_______|\|_______|\|_______|\|__|\|__|
#                                                                                                           
#############################################################################################################

#===============================================================================
# Subscriber
#===============================================================================
class Subscriber(SystemThread, SchedTask):
    
    def __init__(self, controller):
        SystemThread.__init__(self)
        SchedTask.__init__(self, 30)
        self.controller = controller
        try: self.socket = create_connection('wss://%s/socket%s' % (self.controller['ip'], self.controller.token), sslopt={'cert_reqs': ssl.CERT_NONE})
        except Exception as e: print str(e); raise AcidipySessionError()
        self.handlers = {}
        
    def close(self):
        self.socket.close()
        self.stop()
        
    def thread(self):
        try:
            data = json.loads(self.socket.recv())
            subscribe_ids = data['subscriptionId']
            if not isinstance(subscribe_ids, list): subscribe_ids = [subscribe_ids]
            subscribe_data = data['imdata']
        except: pass
        else:
            for sd in subscribe_data:
                for class_name in sd:
                    acidipy_obj = AcidipyObject(**sd[class_name]['attributes'])
                    acidipy_obj.controller = self.controller
                    acidipy_obj.class_name = class_name
                    acidipy_obj.is_detail = True
                    if class_name in PREPARE_CLASSES:
                        acidipy_obj.__class__ = globals()[PREPARE_CLASSES[class_name]]
                        acidipy_obj.__patch__()
                    for subscribe_id in subscribe_ids:
                        try: self.handlers[subscribe_id].subscribe(acidipy_obj['status'], acidipy_obj)
                        except Exception as e:
                            if self.controller.debug: print('Subscribe : {}'.format(str(e)))
                            continue
    
    def sched(self):
        for subscribe_id in self.events:
            try: self.controller.get('/api/subscriptionRefresh.json?id=%s' % subscribe_id)
            except: continue
    
    def register(self, handler):
        resp = self.controller.session.get(self.controller.url + '/api/class/%s.json?subscription=yes' % handler.class_name)
        if resp.status_code == 200:
            try:
                data = resp.json()
                subscription_id = data['subscriptionId']
                self.handlers[subscription_id] = handler
                self.start()
                return subscription_id
            except: raise AcidipySubscriptionError()
        else: raise AcidipySubscriptionError()

class SubscribeHandler:
    def subscribe(self, status, obj): pass

#===============================================================================
# Controller
#===============================================================================
class Controller(Session, AcidipyObject, SchedTask):
    
    class ControllerActorDesc(dict):
        def __init__(self, controller, dn): dict.__init__(self, dn=dn); self.controller = controller
    
    def __init__(self, ip, user, pwd, conns=1, conn_max=2, debug=False, week=False):
        Session.__init__(self,
                         ip=ip,
                         user=user,
                         pwd=pwd,
                         conns=conns,
                         conn_max=conn_max,
                         debug=debug,
                         week=week)
        AcidipyObject.__init__(self,
                               ip=ip,
                               user=user,
                               pwd=pwd,
                               conns=conns,
                               conn_max=conn_max)
        SchedTask.__init__(self, 300)
        
        self.class_name = 'Controller'
        self.scheduler = Scheduler(10)
        self.subscriber = Subscriber(self)
        
        self.Tenant = TenantActor(Controller.ControllerActorDesc(self, 'uni'))
        
        self.Filter = ControllerFilterActor(self)
        self.Contract = ControllerContractActor(self)
        self.Context = ControllerContextActor(self)
        self.L3External = ControllerL3ExternalActor(self)
        self.BridgeDomain = ControllerBridgeDomainActor(self)
        self.AppProfile = ControllerAppProfileActor(self)
        self.FilterEntry = ControllerFilterEntryActor(self)
        self.Subject = ControllerSubjectActor(self)
        self.Subnet = ControllerSubnetActor(self)
        self.EPG = ControllerEPGActor(self)
        self.Endpoint = ControllerEndpointActor(self)
        
        self.Pod = PodActor(Controller.ControllerActorDesc(self, 'topology'))
        
        self.Node = ControllerNodeActor(self)
        self.Paths = ControllerPathsActor(self)
        self.VPaths = ControllerVPathsActor(self)
        self.Path = ControllerPathActor(self)
        self.System = ControllerSystemActor(self)
        self.PhysIf = ControllerPhysIfActor(self)
        
        self.Fault = ControllerFaultActor(self)
        
        self.scheduler.register(self)
        self.scheduler.register(self.subscriber)
        self.scheduler.start()
        
    def close(self):
        self.subscriber.close()
        self.scheduler.stop()
        Session.close(self)
                
    def sched(self): self.refresh()
        
    def detail(self): return self
    
    def health(self):
        url = '/api/node/class/fabricHealthTotal.json?query-target-filter=eq(fabricHealthTotal.dn,"topology/health")'
        data = self.get(url)
        for d in data:
            for class_name in d:
                attrs = d[class_name]['attributes']
                return {'dn' : 'topology', 'name' : 'Total', 'score' : int(attrs['cur'])}
        raise AcidipyNonExistHealth('topology')

    def Class(self, class_name):
        return ControllerActor(self, class_name)
    
    def __call__(self, dn, detail=False):
        url = '/api/mo/' + dn + '.json'
        if not detail: url += '?rsp-prop-include=naming-only'
        data = self.get(url)
        for d in data:
            for class_name in d:
                acidipy_obj = AcidipyObject(**d[class_name]['attributes'])
                acidipy_obj.controller = self
                acidipy_obj.class_name = class_name
                acidipy_obj.is_detail = detail
                if class_name in PREPARE_CLASSES:
                    acidipy_obj.__class__ = globals()[PREPARE_CLASSES[class_name]]
                    acidipy_obj.__patch__()
                return acidipy_obj
        raise AcidipyNonExistData(dn)

class MultiDomain(dict):
    
    class TenantActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Tenant.list(detail, sort, page, **clause)
            return ret
        def health(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Tenant.health()
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Tenant.count()
            return ret
    
    class FilterActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Filter.list(detail, sort, page, **clause)
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Filter.count()
            return ret
    
    class ContractActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Contract.list(detail, sort, page, **clause)
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Contract.count()
            return ret
    
    class ContextActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Context.list(detail, sort, page, **clause)
            return ret
        def health(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Context.health()
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Context.count()
            return ret
    
    class L3ExternalActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].L3External.list(detail, sort, page, **clause)
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].L3External.count()
            return ret
        
    class BridgeDomainActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].BridgeDomain.list(detail, sort, page, **clause)
            return ret
        def health(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].BridgeDomain.health()
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].BridgeDomain.count()
            return ret
    
    class AppProfileActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].AppProfile.list(detail, sort, page, **clause)
            return ret
        def health(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].AppProfile.health()
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].AppProfile.count()
            return ret
    
    class FilterEntryActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].FilterEntry.list(detail, sort, page, **clause)
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].FilterEntry.count()
            return ret
    
    class SubjectActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Subject.list(detail, sort, page, **clause)
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Subject.count()
            return ret
    
    class SubnetActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Subnet.list(detail, sort, page, **clause)
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Subnet.count()
            return ret
        
    class EPGActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].EPG.list(detail, sort, page, **clause)
            return ret
        def health(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].EPG.health()
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].EPG.count()
            return ret
    
    class EndpointActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Endpoint.list(detail, sort, page, **clause)
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Endpoint.count()
            return ret
    
    class PodActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Pod.list(detail, sort, page, **clause)
            return ret
        def health(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Pod.health()
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Pod.count()
            return ret
    
    class NodeActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Node.list(detail, sort, page, **clause)
            return ret
        def health(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Node.health()
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Node.count()
            return ret
        
    class PathsActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Paths.list(detail, sort, page, **clause)
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Paths.count()
            return ret
    
    class VPathsActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].VPaths.list(detail, sort, page, **clause)
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].VPaths.count()
        
    class PathActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Path.list(detail, sort, page, **clause)
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Path.count()
        
    class SystemActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].System.list(detail, sort, page, **clause)
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].System.count()
    
    class PhysIfActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].PhysIf.list(detail, sort, page, **clause)
            return ret
        def health(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].PhysIf.health()
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].PhysIf.count()
            return ret
        
    class ClassActor:
        def __init__(self, multidom, class_name): self.multidom = multidom; self.class_name = class_name
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Class(self.class_name).list(detail, sort, page, **clause)
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Class(self.class_name).count()
            return ret
        
    class FaultActor:
        def __init__(self, multidom): self.multidom = multidom
        def list(self, detail=False, sort=None, page=None, **clause):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Fault.list(detail, sort, page, **clause)
            return ret
        def count(self):
            ret = {}
            for dom_name in self.multidom: ret[dom_name] = self.multidom[dom_name].Fault.count()
            return ret
    
    def __init__(self, conns=1, conn_max=2, debug=False, week=False):
        dict.__init__(self)
        self.conns = conns
        self.conn_max = conn_max
        self.debug = debug
        self.week = week
        
        self.Tenant = MultiDomain.TenantActor(self)
        
        self.Filter = MultiDomain.FilterActor(self)
        self.Contract = MultiDomain.ContractActor(self)
        self.Context = MultiDomain.ContextActor(self)
        self.L3External = MultiDomain.L3ExternalActor(self)
        self.BridgeDomain = MultiDomain.BridgeDomainActor(self)
        self.AppProfile = MultiDomain.AppProfileActor(self)
        self.FilterEntry = MultiDomain.FilterEntryActor(self)
        self.Subject = MultiDomain.SubjectActor(self)
        self.Subnet = MultiDomain.SubnetActor(self)
        self.EPG = MultiDomain.EPGActor(self)
        self.Endpoint = MultiDomain.EndpointActor(self)
        
        self.Pod = MultiDomain.PodActor(self)
        
        self.Node = MultiDomain.NodeActor(self)
        self.Paths = MultiDomain.PathsActor(self)
        self.VPaths = MultiDomain.VPathsActor(self)
        self.Path = MultiDomain.PathActor(self)
        self.System = MultiDomain.SystemActor(self)
        self.PhysIf = MultiDomain.PhysIfActor(self)
        
        self.Fault = MultiDomain.FaultActor(self)
        
    def Class(self, class_name):
        return MultiDomain.ClassActor(self, class_name)
    
    def detail(self): return self
    
    def health(self):
        ret = {}
        for dom_name in self: ret[dom_name] = self[dom_name].health()
        return ret
        
    def addDomain(self, domain_name, ip, user, pwd, conns=None, conn_max=None, debug=None, week=None):
        if domain_name in self: return False
        opts = {'ip' : ip, 'user' : user, 'pwd' : pwd, 'conns' : self.conns, 'conn_max' : self.conn_max, 'debug' : self.debug, 'week' : self.week}
        if conns != None: opts['conns'] = conns
        if conn_max != None: opts['conn_max'] = conn_max
        if debug != None: opts['debug'] = debug
        if week != None: opts['week'] = week
        try: ctrl = Controller(**opts)
        except: return False
        self[domain_name] = ctrl
        return True
    
    def delDomain(self, domain_name):
        if domain_name not in self: return False
        self[domain_name].close()
        self.pop(domain_name)
        return True
    
    def close(self):
        dom_names = self.keys()
        for dom_name in dom_names: self.delDomain(dom_name)
        
        
        
        
        
        
        
         
