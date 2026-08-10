// RollDice.js File
import { Component } from 'react';
import './RollDice.css';
import Die from './Die';

interface RollDiceProps {
  sides?: number[];
  onRoll?: (value: number) => void;
  /** Blocks rolling entirely -- e.g. once this turn's roll is already spent. */
  disabled?: boolean;
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

  /**
   * Resolves with the rolled value once the animation finishes, or undefined
   * if the roll was blocked (disabled / already mid-roll) -- so a caller that
   * needs the actual number afterward (e.g. a voice command chaining a move
   * onto the same roll) can await it directly, instead of only getting the
   * value via onRoll's fire-and-forget callback.
   */
  roll(): Promise<number | undefined> {
    const {
      sides = RollDice.defaultProps.sides ?? [],
      onRoll,
      disabled,
    } = this.props;
    if (disabled || this.state.rolling) {
      return Promise.resolve(undefined);
    }
    this.setState({ rolling: true });

    return new Promise(resolve => {
      setTimeout(() => {
        const value =
          sides[Math.floor(Math.random() * sides.length)];
        this.setState({
          // Changing state upon click
          die1: value,
          rolling: false,
        });
        onRoll?.(value);
        resolve(value);
      }, 1000);
    });
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
          disabled={this.state.rolling || this.props.disabled}
          onClick={this.roll}
        >
          {this.state.rolling ? 'Rolling' : 'Roll Dice!'}
        </button>
      </div>
    );
  }
}

export default RollDice;
