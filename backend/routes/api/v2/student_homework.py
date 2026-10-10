"""Child-scoped paper review and homework corrections; originals are parent-only."""
from flask import Blueprint,jsonify,request
from core.errors import ApiError
from schemas.auth import bearer_token,json_body
from routes.api.v1.homework import endpoint,private_asset,service

student_homework_bp=Blueprint('student_homework_v2',__name__)

@student_homework_bp.get('/homework')
@endpoint
def index():
    return jsonify(service().list_student(bearer_token(request)))

@student_homework_bp.get('/homework/<identity>')
@endpoint
def detail(identity):
    return jsonify(service().student_detail(bearer_token(request),identity))

@student_homework_bp.get('/homework/<identity>/pages/<page_id>/image')
@endpoint
def image(identity,page_id):
    # This route has one representation: the current normalized, rotated and
    # cropped paper. A query can never select the stored pre-edit original.
    if request.args:
        raise ApiError('homework_image_query_unsupported','作业回顾图片不支持查询参数',400)
    return private_asset(service().image(bearer_token(request),identity,page_id,student=True))

@student_homework_bp.post('/homework/<identity>/items/<item_id>/actions')
@endpoint
def action(identity,item_id):
    return jsonify(service().student_action(bearer_token(request),identity,item_id,json_body(request)))

@student_homework_bp.post('/homework/<identity>/items/<item_id>/answers')
@endpoint
def answer(identity,item_id):
    return jsonify(service().student_answer(bearer_token(request),identity,item_id,json_body(request)))

@student_homework_bp.get('/homework/<identity>/items/<item_id>/audio/<kind>')
@endpoint
def audio(identity,item_id,kind):
    return private_asset(service().audio_asset(bearer_token(request),identity,item_id,kind,student=True))

@student_homework_bp.post('/homework-captures')
@endpoint
def capture():
    return jsonify(service().capture_service.capture(bearer_token(request),json_body(request))),202

@student_homework_bp.get('/homework/<identity>/items/<item_id>/tutor')
@endpoint
def tutor_detail(identity,item_id):
    return jsonify(service().tutor.get(bearer_token(request),identity,item_id))

@student_homework_bp.post('/homework/<identity>/items/<item_id>/tutor')
@endpoint
def tutor_turn(identity,item_id):
    return jsonify(service().tutor.submit(bearer_token(request),identity,item_id,json_body(request))),202

@student_homework_bp.get('/homework/<identity>/items/<item_id>/tutor/<turn_id>/audio')
@endpoint
def tutor_audio(identity,item_id,turn_id):
    return private_asset(service().tutor.audio(bearer_token(request),identity,item_id,turn_id))

@student_homework_bp.post('/homework/<identity>/items/<item_id>/tutor/<turn_id>/audio')
@endpoint
def tutor_resume_audio(identity,item_id,turn_id):
    return jsonify(service().tutor.resume_audio(bearer_token(request),identity,item_id,turn_id,json_body(request))),202
