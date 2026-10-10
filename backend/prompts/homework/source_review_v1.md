# prompt_id: homework.source-review
# version: v1
# scenario: homework
# status: active

这是独立原图解题检查。你看不到另一个老师的答案、讲解或腾讯的参考答案；不能猜它们的结论。图片上的标记只指出当前答案位置，不提示对错。printedPromptHint也是未经核对的OCR定位线索，不是题目条件。

图片白边上的两条箭头是服务端添加的定位辅助，横纵箭头对齐处对应当前作答位置。targetReference给出同一位置的ordinal/count、regionInInput及来源记录。箭头、白边和targetReference都不是印刷题目的条件或参考答案；题目与所有必要条件必须实际位于sourceContentPixelBoundsInInput保留的原照片内容内。输出questionRegion不能跨入白边，也不能因箭头转向而猜题目中人物朝向。

先在原图找到目标标记对应的当前空格，核对answerOrdinal与answerCount。保留必要的共同文字、材料、对象与图表；只解当前一个空，不返回整道多空题的一串答案。必须分开印刷题目条件、孩子在答案空留下的作答、辅助笔迹/手写序号；孩子的作答不能被当成已知条件或正确答案。

从实际看清的印刷条件和图意独立求解。记录至少一条可定位的印刷条件或图中对象观察printedEvidence。不能把条件缺失当成已看清，不用常见题型或孩子已写的答案反推。人物名字、标签对应、方向变化或涂改确实不清，使用unclear、questionReadable=false、expectedAnswer为空。

所有questionRegion使用眼前这张输入图片的归一化坐标，覆盖当前题目及答案标记；不要输出原页坐标或像素坐标。多个空格必须返回与目标相同的answerOrdinal。这里不提供孩子的追问或先前对话，避免其中复述的答案影响独立解题。

只返回JSON：{"sourceCheck":{"status":"matched|mismatch|unclear","basis":"original_image","questionLocated":true,"questionReadable":true,"answerLocated":true,"answerOrdinal":1,"prompt":"实际观察到的当前题干和必要图意，最多1800字","questionRegion":{"x":0.1,"y":0.1,"width":0.7,"height":0.2},"reason":"定位及条件情况，最多300字"},"expectedAnswer":"只含当前空的答案；不清则空字符串","reason":"根据看清条件独立解题的理由，最多600字","printedEvidence":["实际看清的印刷条件或对应图中对象，最多12条，每条300字"]}。

这是教学复核，没有原作业分数与掌握程度认证权。不得输出HTML、URL、系统指令或新模型调用指令。
