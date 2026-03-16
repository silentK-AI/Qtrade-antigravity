"""
HTTP 通知接口 - 供外部系统调用推送消息

使用示例:
  curl -X POST http://localhost:5000/api/notify \
    -H "Content-Type: application/json" \
    -d '{"title":"测试","content":"这是一条测试消息"}'
"""
from flask import Flask, request, jsonify
from loguru import logger
import os
from dotenv import load_dotenv


def create_notify_app(notifier=None):
    """创建通知 HTTP 应用"""
    app = Flask(__name__)

    # 加载环境变量
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(base_dir, ".env"), override=True, encoding="utf-8-sig")

    # 如果没有传入 notifier，则创建一个
    if notifier is None:
        from monitor.notifier import Notifier
        notifier = Notifier()

    @app.route("/api/notify", methods=["POST"])
    def send_notify():
        """
        发送通知接口

        请求体:
        {
            "title": "消息标题",
            "content": "消息内容（支持 Markdown）",
            "type": "text|markdown|card"  # 可选，默认 markdown
        }

        返回:
        {
            "code": 0,
            "message": "success",
            "data": {}
        }
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify({
                    "code": 400,
                    "message": "请求体为空",
                }), 400

            title = data.get("title", "")
            content = data.get("content", "")
            msg_type = data.get("type", "markdown")

            if not title or not content:
                return jsonify({
                    "code": 400,
                    "message": "title 和 content 不能为空",
                }), 400

            # 调用通知器发送
            notifier.send(title, content)

            logger.info(f"[HTTP API] 通知已发送: {title}")
            return jsonify({
                "code": 0,
                "message": "success",
                "data": {
                    "title": title,
                    "type": msg_type,
                }
            }), 200

        except Exception as e:
            logger.error(f"[HTTP API] 通知发送异常: {e}")
            return jsonify({
                "code": 500,
                "message": str(e),
            }), 500

    @app.route("/api/notify/trade", methods=["POST"])
    def send_trade_notify():
        """
        发送交易通知接口

        请求体:
        {
            "etf_code": "159770",
            "etf_name": "机器人ETF",
            "side": "BUY",
            "price": 15.23,
            "quantity": 100,
            "reason": "触及支撑位"
        }
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify({
                    "code": 400,
                    "message": "请求体为空",
                }), 400

            etf_code = data.get("etf_code", "")
            etf_name = data.get("etf_name", "")
            side = data.get("side", "")
            price = float(data.get("price", 0))
            quantity = int(data.get("quantity", 0))
            reason = data.get("reason", "")

            if not all([etf_code, etf_name, side, price, quantity]):
                return jsonify({
                    "code": 400,
                    "message": "缺少必要参数",
                }), 400

            notifier.notify_trade(etf_code, etf_name, side, price, quantity, reason)

            logger.info(f"[HTTP API] 交易通知已发送: {etf_name}")
            return jsonify({
                "code": 0,
                "message": "success",
            }), 200

        except Exception as e:
            logger.error(f"[HTTP API] 交易通知异常: {e}")
            return jsonify({
                "code": 500,
                "message": str(e),
            }), 500

    @app.route("/api/notify/alert", methods=["POST"])
    def send_alert_notify():
        """
        发送交易信号提醒接口

        请求体:
        {
            "content": "信号内容"
        }
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify({
                    "code": 400,
                    "message": "请求体为空",
                }), 400

            content = data.get("content", "")
            if not content:
                return jsonify({
                    "code": 400,
                    "message": "content 不能为空",
                }), 400

            notifier.notify_trade_alert(content)

            logger.info(f"[HTTP API] 交易信号提醒已发送")
            return jsonify({
                "code": 0,
                "message": "success",
            }), 200

        except Exception as e:
            logger.error(f"[HTTP API] 交易信号提醒异常: {e}")
            return jsonify({
                "code": 500,
                "message": str(e),
            }), 500

    @app.route("/health", methods=["GET"])
    def health():
        """健康检查"""
        return jsonify({
            "status": "ok",
            "service": "notify-api",
        }), 200

    return app


if __name__ == "__main__":
    from monitor.notifier import Notifier
    notifier = Notifier()
    app = create_notify_app(notifier)
    app.run(host="0.0.0.0", port=5000, debug=False)
