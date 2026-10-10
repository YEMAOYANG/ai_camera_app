"""Parent homework routes. Ownership and role checks stay in the domain service."""
from functools import wraps
from flask import Blueprint, jsonify, make_response, request
from core.errors import ApiError,error_response
from schemas.auth import bearer_token,json_body

homework_bp=Blueprint('homework_v1',__name__)

def service():
    from services.service_factory import homework_service
    return homework_service()

def endpoint(fn):
    @wraps(fn)
    def invoke(*args,**kwargs):
        try:
            return fn(*args,**kwargs)
        except ApiError as error:
            return error_response(error)
    return invoke

def private_asset(value):
    body,mime=value
    response=make_response(body)
    response.headers['Content-Type']=mime
    response.headers['Cache-Control']='private, no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Content-Security-Policy']="default-src 'none'"
    return response

@homework_bp.route('/children/<child_id>/homework-submissions',methods=['GET','POST'])
@endpoint
def submissions(child_id):
    svc=service(); token=bearer_token(request)
    return jsonify(svc.create(token,child_id,json_body(request)) if request.method=='POST' else svc.list_parent(token,child_id))

@homework_bp.route('/homework-submissions/<identity>',methods=['GET','DELETE'])
@endpoint
def submission(identity):
    svc=service(); token=bearer_token(request)
    return jsonify(svc.delete(token,identity,json_body(request)) if request.method=='DELETE' else svc.get(token,identity))

@homework_bp.route('/homework-submissions/<identity>/pages',methods=['POST','PATCH'])
@endpoint
def pages(identity):
    svc=service(); token=bearer_token(request)
    if request.method=='PATCH':
        return jsonify(svc.update_pages(token,identity,json_body(request)))
    limit=svc.policy['maxUploadBytes']
    if request.content_length is not None and request.content_length>limit+65536:
        raise ApiError('homework_image_too_large','作业图片过大，请压缩后上传',413)
    file=request.files.get('file')
    if file is None:
        raise ApiError('homework_image_required','请选择作业图片',400)
    data=request.form.to_dict()
    try:
        data['revision']=int(data.get('revision',''))
    except ValueError:
        raise ApiError('homework_revision_conflict','请携带作业版本',400)
    return jsonify(svc.upload(token,identity,data,file.read(limit+1)))

@homework_bp.post('/homework-submissions/<identity>/analyze')
@endpoint
def analyze(identity):
    return jsonify(service().analyze(bearer_token(request),identity,json_body(request))),202

@homework_bp.patch('/homework-submissions/<identity>/items/<item_id>')
@endpoint
def correct_item(identity,item_id):
    return jsonify(service().correct_recognition(bearer_token(request),identity,item_id,json_body(request)))

@homework_bp.get('/homework-submissions/<identity>/pages/<page_id>/image')
@endpoint
def image(identity,page_id):
    return private_asset(service().image(bearer_token(request),identity,page_id,original=request.args.get('original')=='1'))

@homework_bp.get('/homework-submissions/<identity>/items/<item_id>/audio/<kind>')
@endpoint
def audio(identity,item_id,kind):
    return private_asset(service().audio_asset(bearer_token(request),identity,item_id,kind))

@homework_bp.route('/children/<child_id>/homework-capture-authorization',methods=['GET','PUT'])
@endpoint
def capture_authorization(child_id):
    svc=service(); token=bearer_token(request)
    return jsonify(svc.capture_service.authorize(token,child_id,json_body(request)) if request.method=='PUT'
        else svc.capture_service.parent_authorizations(token,child_id))
