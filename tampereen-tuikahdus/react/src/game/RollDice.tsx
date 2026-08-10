// RollDice.js File
import React, { Component } from 'react';
import './RollDice.css';
import Die from './Die';

interface RollDiceProps {
  sides?: number[];
  onRoll?: (value: number) => void;
}

interface RollDiceState {
  die1: number;
  rolling: boolean;
}

class RollDice extends Component<
  RollDiceProps,
  RollDiceState
> {
  // Face numbers passes as default props
  static defaultProps: RollDiceProps = {
    sides: [1, 2, 3, 4, 5, 6],
  };

  constructor(props: RollDiceProps) {
    super(props);

    // States
    this.state = {
      die1: 1,
      rolling: false,
    };
    this.roll = this.roll.bind(this);
  }

  roll() {
    const {
      sides = RollDice.defaultProps.sides ?? [],
      onRoll,
    } = this.props;
    this.setState({ rolling: true });

    setTimeout(() => {
      const value =
        sides[Math.floor(Math.random() * sides.length)];
      this.setState({
        // Changing state upon click
        die1: value,
        rolling: false,
      });
      onRoll?.(value);
    }, 1000);
  }

  render() {
    const handleBtn = this.state.rolling
      ? 'RollDice-rolling'
      : '';
    const { die1, rolling } = this.state;
    return (
      <div className='RollDice'>
        <div className='RollDice-container'>
          <Die face={die1} rolling={rolling} />
        </div>
        <button
          className={handleBtn}
          disabled={this.state.rolling}
          onClick={this.roll}
        >
          {this.state.rolling ? 'Rolling' : 'Roll Dice!'}
        </button>
      </div>
    );
  }
}

export default RollDice;
