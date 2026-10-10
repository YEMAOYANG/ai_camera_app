# prompt_id: homework.source-review
# version: v3
# scenario: homework
# status: active

独立查看当前输入图片。白边横纵箭头对齐处是当前答案空；箭头只定位，不是印刷条件或对错提示。targetReference.ordinal/count 给出当前空在这道题中的顺序，只解这一个空。

箭头指向孩子填写的空，不代表孩子写对了。expectedAnswer必须重新依据印刷题干和印刷图案求解，不能直接抄该空内的手写数字。数图题先逐个数实际印刷对象，再回答当前空；不要把全图总数、辅助编号或孩子已写的个数当答案。

先看清原照片的印刷题干、对象和必要条件。孩子已填答案与手写编号不是已知条件。printedPromptHint 只是未经核对的定位线索，不能替代实际图意。看不清人物名字、朝向、涂改或必要条件就返回unclear，不猜答案。

只有一个坐标系：眼前输入图片左上为(0,0)，右下为(1,1)。targetReference.regionInInput 是当前答案空；questionRegionInInput 是服务端保留的共同题目范围。亲自确认题目可见后，questionRegion 优先使用 questionRegionInInput，不必另猜坐标；它须覆盖当前空及必要条件，并完全位于 sourceContentPixelBoundsInInput 的原照片内容内。没有原页坐标，不输出像素坐标，不跨入白边。

只返回以下JSON结构，每个键一次，各字段不得复制到其他层级。sourceCheck 中只放示例的8个字段，questionRegion 后就闭合 sourceCheck；reason、expectedAnswer、printedEvidence 只放在根对象。expectedAnswer 只含当前空的单一答案，不含其他空的答案或解题步骤。printedEvidence 至少记录一条亲自看清的印刷条件或图中对象，不能抄孩子答案当证据。

{"sourceCheck":{"status":"matched","basis":"original_image","questionLocated":true,"questionReadable":true,"answerLocated":true,"answerOrdinal":1,"prompt":"实际看清的当前小题和必要条件，最多1800字","questionRegion":{"x":0.1,"y":0.1,"width":0.7,"height":0.2}},"expectedAnswer":"当前空的单一答案","reason":"基于原图独立求解的理由，最多600字","printedEvidence":["看清的印刷条件或对应图中对象，最多12条，每条300字"]}

未看清时status为unclear，相应Located/Readable为false，expectedAnswer为空字符串，说明实际限制。仅返回JSON，不添加Markdown、其他根字段、嵌套解答对象或重复键。
