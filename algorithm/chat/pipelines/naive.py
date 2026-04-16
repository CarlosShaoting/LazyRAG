from typing import List
import lazyllm
from lazyllm import pipeline, bind, ifs

from chat.pipelines.builders import get_ppl_search, get_ppl_generate, get_automodel
from chat.components.process.multiturn_query_rewriter import MultiturnQueryRewriter
from chat.utils.load_config import get_retrieval_settings


def get_ppl_naive(url: str, retriever_configs: List[dict] = None, stream=False):
    if retriever_configs is None:
        retriever_configs = get_retrieval_settings().retriever_configs

    with lazyllm.save_pipeline_result():
        with pipeline() as rag_ppl:
            rag_ppl.rewriter = ifs(
                lambda x: x.get('history'),
                tpath=MultiturnQueryRewriter(llm=get_automodel('llm_instruct'))
                | bind(
                    priority=rag_ppl.input['priority'],
                    has_appendix=bool(rag_ppl.input['image_files'])
                    or bool(rag_ppl.input['files']),
                ),
                fpath=lambda x: x,
            )
            rag_ppl.search = get_ppl_search(url, retriever_configs)
            rag_ppl.generate = get_ppl_generate(stream=stream) | bind(
                image_files=[],
                query=rag_ppl.input['query'],
                history=rag_ppl.input['history'],
                debug=rag_ppl.input['debug'],)

    return rag_ppl

if __name__ == "__main__":
    # import lazyllm
    # def get_remote_docment(url, name="__default__"):
    #     return lazyllm.Document(url=f"{url}/_call", name=name)

    # url = "http://10.119.16.66:9012,tyy_0302"
    url="http://10.119.16.66:9003,research_center_0131_a"
    # url = "http://10.119.16.66:9102,quantum_0131_a"
    rag_ppl = get_ppl_naive(url, stream=False)
    params = {
        "filters": {},
        "query": "冠忠巴士集團 2024 年上半年收入增長 24.5%，但除稅前溢利卻由 19,646 千港元下降至 10,407 千港元。請分析造成此「增收不增利」現象的主要原因，並指出哪一業務分類的表現惡化最顯著",  # 高速铁路铁路直线地段标准路基面宽度如何按规范标准表取值？
        "files": [],
        "history": [],
        "debug": False
    }
    result = rag_ppl(params)
    print(result['sources'])
    print('--------------------------------')
    print(result['text'])