"""Experimental transport annotations for multi-image order, with recorded sampling."""
import copy
from qwen38_client import Qwen38Client


class LabeledQwen38Client(Qwen38Client):
    def __init__(self,*args,image_labels=True,greedy=False,**kwargs):
        super().__init__(*args,**kwargs)
        self.image_labels=image_labels
        self.greedy=greedy

    def _request_json(self,path,payload=None):
        if path == '/chat/completions' and payload is not None:
            payload=copy.deepcopy(payload)
            if self.greedy:
                payload.update(temperature=0.0,top_p=1.0,top_k=1,presence_penalty=0.0)
            if self.image_labels:
                for message in payload['messages']:
                    original=message['content'];content=[];index=0
                    for item in original:
                        if item['type']=='image_url':
                            index+=1
                            content.append({'type':'text','text':f'INPUT IMAGE {index} (position {index} in the supplied sequence):'})
                            content.append(item)
                            content.append({'type':'text','text':f'END INPUT IMAGE {index}.'})
                        else:content.append(item)
                    content.append({'type':'text','text':'Use the supplied image order exactly. First/left means INPUT IMAGE 1; second/right means INPUT IMAGE 2. Do not reorder pages to fit an inferred document sequence.'})
                    message['content']=content
        return super()._request_json(path,payload)

    def model_details(self):
        result=super().model_details()
        result['input_image_labels']='positional_v1' if self.image_labels else 'none'
        if self.greedy:
            result['generation'].update(temperature=0.0,top_p=1.0,top_k=1,presence_penalty=0.0)
        return result


def load_model(model_path,logger,revision=None,inference=None):
    """Loader for isolated labeled-image trials; production loader is untouched."""
    if not inference or inference.get('backend')!='qwen38' or inference.get('thinking')!='off':
        raise ValueError('Labeled trial requires Qwen3.8 thinking off')
    from model_options import validate_deployment, RESPONSE_RECOVERY_POLICY
    if inference.get('response_recovery',RESPONSE_RECOVERY_POLICY)!=RESPONSE_RECOVERY_POLICY:
        raise ValueError('Qwen3.8 response-recovery policy differs from this client')
    d=validate_deployment(inference['deployment'])
    if model_path!=d['served_model'] or revision!=d['revision']:
        raise ValueError('Model or revision mismatch')
    greedy=inference.get('experimental_greedy',False)
    if type(greedy) is not bool:raise ValueError('Expected Boolean greedy setting')
    c=LabeledQwen38Client(inference['endpoint'],model_path,d,thinking='off',
                         max_completion_tokens=inference['max_completion_tokens'],
                         timeout_seconds=inference['timeout_seconds'],image_labels=True,greedy=greedy)
    c.verify();logger.info('Labeled Qwen3.8 ready: %s',model_path)
    return c,None,{'backend':'qwen38'}
