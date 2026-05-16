// 报警弹窗组件 - Class Component 版（故意留个 class 的）
import React from 'react';
import { Alert } from 'antd';

const levelMap = {
  warn1: { type: 'warning', txt: '⚠️ 预警' },
  warn2: { type: 'error', txt: '🚨 警告' },
  jiting: { type: 'error', txt: '🛑 紧急停注!' },
};

class AlarmToast extends React.Component {
  componentDidUpdate(prevProps) {
    // 如果有新报警，3秒后清
    if (this.props.info && this.props.info !== prevProps.info) {
      this.timer = setTimeout(() => {
        if (this.props.onClear) this.props.onClear();
      }, 6000);
    }
  }

  componentWillUnmount() {
    if (this.timer) clearTimeout(this.timer);
  }

  render() {
    const { info } = this.props;
    if (!info) return null;
    const cfg = levelMap[info.level] || levelMap.warn1;
    return (
      <div className="alarm-toast-overlay">
        <div className="alarm-toast-box">
          <Alert
            message={cfg.txt}
            description={info.msg || '报警触发，请检查！'}
            type={cfg.type}
            showIcon
            closable
          />
        </div>
      </div>
    );
  }
}

export default AlarmToast;
